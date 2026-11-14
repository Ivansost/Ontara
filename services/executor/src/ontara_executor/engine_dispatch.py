"""Authenticated internal notifier -> pinned Agent Engine invocation API."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import uuid

import httpx


class EngineDispatcher:
    ACCEPT = "application/vnd.agent-engine-2026-09-20-preview+json"
    BASE = "https://agentengine.mongodb.com"

    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.active_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self._token: str | None = None
        self._token_until = 0

    async def start(self, *, job_id=None, case_id=None, recover=True):
        if not job_id and not case_id:
            raise ValueError("An approved jobId or caseId is required")
        for name in ("AGENT_ENGINE_CLIENT_ID", "AGENT_ENGINE_CLIENT_SECRET", "AGENT_ENGINE_PROJECT_ID", "AGENT_ENGINE_WORKSPACE_ID"):
            if not os.environ.get(name):
                raise ValueError("Agent Engine invocation configuration is incomplete")
        async with self.lock:
            if self.active_task and not self.active_task.done():
                raise RuntimeError("The free executor already has one active browser workflow")
            task_id = f"engine-{uuid.uuid4().hex}"
            task = {"taskId": task_id, "jobId": job_id, "caseId": case_id, "status": "starting", "runtimeMode": "engine", "attempts": []}
            self.tasks[task_id] = task
            self.active_task = asyncio.create_task(self._invoke(task, job_id, case_id, recover))
            return task

    async def _access_token(self, client):
        if self._token and time.monotonic() < self._token_until:
            return self._token
        response = await client.post(self.BASE + "/api/v1/oauth/token", data={"grant_type": "client_credentials", "client_id": os.environ["AGENT_ENGINE_CLIENT_ID"], "client_secret": os.environ["AGENT_ENGINE_CLIENT_SECRET"]})
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._token_until = time.monotonic() + max(0, int(data.get("expires_in", 60)) - 30)
        return self._token

    async def _invoke(self, task, job_id, case_id, recover):
        project_id = os.environ["AGENT_ENGINE_PROJECT_ID"]
        workspace_id = os.environ["AGENT_ENGINE_WORKSPACE_ID"]
        if any(not value.replace("-", "").replace("_", "").isalnum() for value in (project_id, workspace_id)):
            task.update(status="failed", errorType="InvalidEngineIdentifier")
            return
        path = f"/api/v1/projects/{project_id}/workspaces/{workspace_id}/invoke"
        payload = {k: v for k, v in {"jobId": job_id, "caseId": case_id}.items() if v}
        session = "ontara_" + (job_id or case_id)
        if len(session) > 128 or not session.replace("_", "").replace("-", "").isalnum():
            task.update(status="failed", errorType="InvalidSessionIdentifier")
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=20), follow_redirects=False) as client:
            for number in range(2 if recover else 1):
                attempt = {"number": number + 1}
                task["attempts"].append(attempt)
                try:
                    token = await self._access_token(client)
                    task["status"] = "running"
                    response = await client.post(self.BASE + path, headers={"Authorization": "Bearer " + token, "Accept": self.ACCEPT, "X-Session-ID": session}, json={"message": json.dumps(payload)})
                    attempt["httpStatus"] = response.status_code
                    response.raise_for_status()
                    result = response.json()
                    attempt.update(status=result.get("status"), executionId=result.get("execution_id"))
                    if result.get("status") in {"completed", "suspended"}:
                        task["status"] = result["status"]
                        # Only the deterministic bounded graph's status is exposed.
                        with contextlib.suppress(ValueError, TypeError):
                            output = json.loads(result.get("response", ""))
                            attempt["result"] = {k: output[k] for k in ("status", "operation_id", "attempt_id", "process_id") if k in output}
                        return
                    task["status"] = "engine_execution_failed"
                except Exception as error:
                    task.update(status="engine_invocation_failed", errorType=type(error).__name__)
                    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500:
                        return
                if not recover or number:
                    return
                # Native Engine process restarts are platform-managed. A fresh
                # invocation can lease the same unresolved operation after its
                # short lease expires, then must reconcile before any write.
                task["status"] = "waiting_for_fresh_process"
                await asyncio.sleep(int(os.environ.get("ONTARA_LEASE_SECONDS", "15")) + 1)

    async def close(self):
        if self.active_task:
            self.active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.active_task
