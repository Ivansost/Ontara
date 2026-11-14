import asyncio
import json
import os
from ontara_executor.supervisor import ChildSupervisor


async def test_case_only_crash_recovery_preserves_checkpoint_thread(monkeypatch):
    import ontara_executor.supervisor as module
    commands = []
    class Process:
        def __init__(self, number):
            self.pid = 41000 + number
            self.returncode = -9 if number == 1 else 0
        async def communicate(self):
            return (json.dumps({"status": "receipt_verified", "process_id": self.pid}).encode(), b"")
    async def spawn(*command, **kwargs):
        commands.append(command)
        guard = {"jobId": "discovered-job", "caseId": "case-only", "operationId": "op-only", "workerId": "private-worker", "leaseToken": "private-guard", "processId": 41001, "attemptId": "attempt-first"}
        os.write(kwargs["pass_fds"][0], (json.dumps(guard) + "\n").encode())
        return Process(len(commands))
    class Backend:
        async def request(self, *args, **kwargs):
            return {"requeued": True}
        async def event(self, *args, **kwargs):
            pass
        async def close(self):
            pass
    monkeypatch.setenv("ONTARA_RUNTIME_MODE", "fallback")
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(module.BackendClient, "from_env", lambda: Backend())
    supervisor = ChildSupervisor()
    task = await supervisor.start(case_id="case-only")
    await supervisor.active_task
    assert len(commands) == 2
    assert [command[command.index("--thread-id") + 1] for command in commands] == ["case-only", "case-only"]
    assert "--job-id" not in commands[0]
    assert commands[1][commands[1].index("--job-id") + 1] == "discovered-job"
    assert task["status"] == "receipt_verified"
