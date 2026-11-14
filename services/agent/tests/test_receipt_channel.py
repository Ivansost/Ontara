import json
from ontara_agent.receipt_channel import persist_before_traced_return


class Backend:
    def __init__(self):
        self.writes = []
    async def request(self, method, path, body):
        self.writes.append((method, path, body))
        return {"recorded": True}


async def test_engine_tool_stores_private_receipt_but_never_traces_capability():
    backend = Backend()
    raw = {"status": "accepted", "accepted": True, "receipt": {"receiptId": "receipt-1", "ticketId": "ticket-1", "payloadDigest": "digest-1", "action": "update", "updateUrl": "https://demo.invalid/update?accessToken=private-ticket-capability", "ticketUrl": "https://demo.invalid/ticket?accessToken=private-ticket-capability", "receiptUrl": "https://demo.invalid/receipt?accessToken=private-ticket-capability", "receiptSignature": "private-signature"}}
    request = {"operationId": "op-1", "runId": "run-1", "attemptId": "attempt-1"}
    result = await persist_before_traced_return(raw, request, {"jobId": "job-1", "workerId": "worker-1", "leaseToken": "private-lease"}, backend)
    serialized = json.dumps(result)
    assert "private-ticket-capability" not in serialized
    assert "private-signature" not in serialized
    assert "private-lease" not in serialized
    assert "updateUrl" not in serialized
    assert result["receiptRecorded"] is True
    assert backend.writes[0][2]["receipt"] == raw["receipt"]


async def test_engine_fault_path_never_stores_receipt_before_process_kill():
    backend = Backend()
    result = await persist_before_traced_return({"status": "accepted", "accepted": True, "receipt": {"updateUrl": "https://demo.invalid/?accessToken=private"}}, {"returnReceipt": False}, {}, backend)
    assert not backend.writes
    assert "receipt" not in result
    assert result["receiptWithheldForCrashProof"] is True
