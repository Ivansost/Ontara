from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import uuid
from datetime import datetime, timezone

from ontara_agent.clients import BackendClient


class ChildSupervisor:
    """An HTTP parent survives real graph-child SIGKILL and starts a fresh child."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.tasks: dict[str, dict] = {}
        self.active_task: asyncio.Task | None = None
        self.process: asyncio.subprocess.Process | None = None

    async def start(self, *, job_id: str | None = None, case_id: str | None = None, recover: bool = True):
        if os.environ.get("ONTARA_RUNTIME_MODE") != "fallback":
            raise ValueError("Cloud supervisor is only enabled for the explicitly selected fallback")
        if not job_id and not case_id:
            raise ValueError("jobId or caseId is required")
        async with self.lock:
            if self.active_task and not self.active_task.done():
                raise RuntimeError("The free executor already has one active browser workflow")
            task_id = f"run-{uuid.uuid4().hex}"
            self.tasks[task_id] = {"taskId": task_id, "status": "starting", "jobId": job_id, "caseId": case_id, "supervisorProcessId": os.getpid(), "startedAt": datetime.now(timezone.utc).isoformat(), "attempts": []}
            self.active_task = asyncio.create_task(self._run(task_id, job_id, case_id, recover))
            return self.tasks[task_id]

    async def _run(self, task_id, job_id, case_id, recover):
        task = self.tasks[task_id]
        for number in range(2 if recover else 1):
            read_fd, write_fd = os.pipe()
            env = dict(os.environ, ONTARA_SUPERVISOR_CONTROL_FD=str(write_fd))
            command = [sys.executable, "-m", "ontara_agent.child"]
            if job_id:
                command.extend(["--job-id", job_id])
            if case_id:
                command.extend(["--case-id", case_id])
            try:
                self.process = await asyncio.create_subprocess_exec(*command, env=env, pass_fds=(write_fd,), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            except Exception as error:
                os.close(read_fd)
                os.close(write_fd)
                task.update(status="failed", errorType=type(error).__name__)
                return
            os.close(write_fd)
            process = self.process
            task["status"] = "running"
            attempt = {"number": number + 1, "processId": process.pid}
            task["attempts"].append(attempt)
            guard_task = asyncio.create_task(asyncio.to_thread(os.read, read_fd, 16384))
            stdout, _ = await process.communicate()
            try:
                control = await guard_task
                lease = json.loads(control.decode().splitlines()[0]) if control else None
            except (ValueError, IndexError):
                lease = None
            finally:
                os.close(read_fd)
            attempt["exitCode"] = process.returncode
            attempt["actualProcessCrash"] = process.returncode == -signal.SIGKILL
            if process.returncode == 0:
                try:
                    last = json.loads(stdout.decode().splitlines()[-1])
                    attempt.update({k: last[k] for k in ("status", "operation_id", "attempt_id", "process_id") if k in last})
                    task["status"] = last.get("status", "completed")
                except (ValueError, IndexError):
                    task["status"] = "completed"
                return
            task["status"] = "child_crashed" if attempt["actualProcessCrash"] else "child_failed"
            if not lease:
                return
            # Exact fencing guard is kept in a private pipe, not this status record.
            backend = BackendClient.from_env()
            try:
                await backend.request("POST", f"/internal/v1/jobs/{lease['jobId']}/abandon", {k: lease[k] for k in ("workerId", "leaseToken", "processId", "attemptId")} | {"reason": "process_exit", "exitCode": process.returncode})
                await backend.event(lease["caseId"], "execution_process_exited", "The execution process exited. A fresh process will reconcile the same operation.", attempt_id=lease["attemptId"], data={"processId": process.pid, "supervisorProcessId": os.getpid(), "exitCode": process.returncode, "actualProcessCrash": attempt["actualProcessCrash"], "operationId": lease["operationId"]})
                job_id = lease["jobId"]
            except Exception as error:
                task.update(status="recovery_requires_attention", errorType=type(error).__name__)
                return
            finally:
                await backend.close()
            if not recover or number:
                return
            task["status"] = "starting_recovery"

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.process.wait(), 10)
        if self.active_task:
            self.active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.active_task
