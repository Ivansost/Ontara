from __future__ import annotations

import os
from typing import Any
import httpx


class ServiceClient:
    def __init__(self, base_url: str, token: str, *, transport=None):
        if not token:
            raise ValueError("ONTARA_INTERNAL_TOKEN is required")
        if not base_url.startswith("https://") and os.environ.get("ONTARA_ALLOW_LOCAL_HTTP") != "1":
            raise ValueError("Internal service calls require HTTPS")
        self.http = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=httpx.Timeout(100, connect=20), follow_redirects=False, transport=transport)

    async def request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict:
        response = await self.http.request(method, path, json=data)
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.http.aclose()


class BackendClient(ServiceClient):
    @classmethod
    def from_env(cls):
        return cls(os.environ["BACKEND_BASE_URL"], os.environ["ONTARA_INTERNAL_TOKEN"])

    async def lease(self, worker_id: str, job_id: str | None, case_id: str | None):
        data = {"workerId": worker_id, "leaseSeconds": int(os.environ.get("ONTARA_LEASE_SECONDS", "15"))}
        if job_id:
            data["jobId"] = job_id
        if case_id:
            data["caseId"] = case_id
        return await self.request("POST", "/internal/v1/jobs/lease", data)

    async def heartbeat(self, job: dict):
        return await self.request("POST", f"/internal/v1/jobs/{job['id']}/heartbeat", self.guard(job) | {"leaseSeconds": int(os.environ.get("ONTARA_LEASE_SECONDS", "15"))})

    @staticmethod
    def guard(job):
        return {"workerId": job["workerId"], "leaseToken": job["leaseToken"]}

    async def transition(self, job, op, state, *, attempt_id, evidence=None):
        result = await self.request("POST", f"/internal/v1/operations/{op['id']}/transition", self.guard(job) | {"jobId": job["id"], "expectedState": op["state"], "state": state, "runId": op["runId"], "attemptId": attempt_id, "evidence": evidence or {}})
        op["state"] = state
        return result

    async def event(self, case_id, kind, message, *, op=None, attempt_id=None, data=None):
        body = {"kind": kind, "message": message, "visibility": "presenter", "data": data or {}}
        if op:
            body.update(operationId=op["id"], runId=op["runId"])
        if attempt_id:
            body["attemptId"] = attempt_id
        return await self.request("POST", f"/internal/v1/cases/{case_id}/events", body)

    async def receipt(self, job, op, receipt, attempt_id):
        return await self.request("POST", f"/internal/v1/operations/{op['id']}/receipt", self.guard(job) | {"jobId": job["id"], "receipt": receipt, "runId": op["runId"], "attemptId": attempt_id})

    async def follow_up(self, case_id, op, question_ids, reason, fingerprint, *, source_event_id=None, ticket_id=None):
        return await self.request("POST", f"/internal/v1/cases/{case_id}/follow-up-request", {"sourceEventId": source_event_id or f"form-{op['id']}-{fingerprint}", "questionIds": question_ids, "reason": reason, "externalTicketId": ticket_id or op.get("externalTicketId"), "operationId": op["id"]})

    async def inspection_result(self, job, status, *, question_ids=None, reason, evidence=None):
        return await self.request("POST", f"/internal/v1/jobs/{job['id']}/inspection-result", self.guard(job) | {"status": status, "questionIds": question_ids or [], "reason": reason, "evidence": evidence or {}})

    async def lessons(self, query):
        return await self.request("POST", "/internal/v1/retrieval/lessons", query)


class BrowserClient(ServiceClient):
    @classmethod
    def from_env(cls):
        return cls(os.environ["EXECUTOR_BASE_URL"], os.environ["ONTARA_INTERNAL_TOKEN"])

    async def call(self, action: str, request: dict):
        if action not in {"inspect", "submit", "reconcile"}:
            raise ValueError("Unsupported browser operation")
        return await self.request("POST", "/internal/v1/browser/" + action, request)
