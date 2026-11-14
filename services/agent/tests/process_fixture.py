"""File-ledger fixture for actual OS-crash tests; never used by the application."""
import asyncio
import json
import os
from pathlib import Path
from ontara_agent.workflow import ExecutionWorkflow

root = Path(os.environ["ONTARA_PROCESS_TEST_ROOT"])


def load(name, default):
    p = root / name
    return json.loads(p.read_text()) if p.exists() else default


def save(name, value):
    (root / name).write_text(json.dumps(value))


class Ledger:
    async def lease(self, worker_id, job_id, case_id):
        state = load("ledger.json", {"state": "prepared", "faultConsumed": False})
        fire = not state["faultConsumed"]
        state["faultConsumed"] = True
        save("ledger.json", state)
        operation = {"id": "op-real-kill", "runId": "run-real-kill", "clientReference": "op-real-kill", "payloadDigest": "a" * 64, "state": state["state"], "action": "create", "portalId": "roads", "caseId": "case-real-kill", "recipientId": "halton", "payload": {"location": {"incidentAddress": "Synthetic road"}, "answers": {"description": "Synthetic damage for actual process test"}}, "route": {}}
        return {"job": {"id": "job-real-kill", "workerId": worker_id, "leaseToken": "private-test-only", "faultAfterAcceptance": fire}, "case": {"id": "case-real-kill"}, "operation": operation}

    async def heartbeat(self, job):
        pass

    async def event(self, *args, **kwargs):
        events = load("events.json", [])
        events.append({"kind": args[1], "attemptId": kwargs.get("attempt_id"), "data": kwargs.get("data")})
        save("events.json", events)

    async def transition(self, job, op, state, **kwargs):
        ledger = load("ledger.json", {})
        ledger["state"] = op["state"] = state
        save("ledger.json", ledger)

    async def receipt(self, job, op, receipt, attempt_id):
        ledger = load("ledger.json", {})
        ledger.update(state="receipt_verified", receipt=receipt, recoveredProcessId=os.getpid())
        save("ledger.json", ledger)


class Tools:
    async def call(self, action, request):
        if action == "inspect":
            return {"status": "observed", "observation": {"formVersion": "1", "fingerprint": "b" * 64, "fields": [{"name": "location", "label": "Location", "type": "text", "required": True}, {"name": "description", "label": "Description", "type": "textarea", "required": True}]}}
        receiver = load("receiver.json", {"createRequestCount": 0, "ticketCount": 0})
        if action == "submit":
            receiver.update(createRequestCount=receiver["createRequestCount"] + 1, ticketCount=1, receipt={"ticketId": "ticket-actual-kill", "receiptId": "receipt-actual-kill", "clientReference": request["clientReference"], "payloadDigest": request["payloadDigest"]})
            save("receiver.json", receiver)
            return {"status": "accepted", "accepted": True}
        if action == "reconcile":
            return {"status": "accepted", "accepted": True, "receipt": receiver["receipt"]}
        raise AssertionError("Unexpected test action")


asyncio.run(ExecutionWorkflow(Ledger(), Tools(), None).run({"job_id": "job-real-kill"}))
