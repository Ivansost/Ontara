"""Keep private receiving capabilities out of SDK-traced tool results."""
from __future__ import annotations


SAFE_RECEIPT_FIELDS = {
    "schemaVersion", "ticketId", "receiptId", "runId", "portalId", "authorityId",
    "routeId", "clientReference", "payloadDigest", "action", "acceptedAt",
    "formVersion", "formPayloadDigest", "formSnapshotDigest", "isDemo",
}


async def persist_before_traced_return(result: dict, request: dict, lease_context: dict, backend) -> dict:
    safe = {key: value for key, value in result.items() if key != "receipt"}
    receipt = result.get("receipt")
    if not result.get("accepted") or not receipt:
        return safe
    if request.get("returnReceipt") is False:
        # The actual process-fault path must not store acceptance first, even if
        # a future browser implementation mistakenly supplies a receipt body.
        safe["receiptWithheldForCrashProof"] = True
        return safe
    if any(not lease_context.get(key) for key in ("jobId", "workerId", "leaseToken")):
        raise ValueError("A current fenced lease is required for private receipt storage")
    await backend.request("POST", f"/internal/v1/operations/{request['operationId']}/receipt", {
        **{key: lease_context[key] for key in ("jobId", "workerId", "leaseToken")},
        "receipt": receipt, "runId": request["runId"], "attemptId": request["attemptId"],
    })
    safe["receipt"] = {key: value for key, value in receipt.items() if key in SAFE_RECEIPT_FIELDS}
    safe["receiptRecorded"] = True
    return safe
