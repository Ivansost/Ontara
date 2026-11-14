"""Explicit manual seeded-demo rehearsal; never imported by the runtime.

The developer supplies a JSON object mapping observed field names to immutable
approved fact IDs. There is no version-specific mapping or runtime bypass here.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import uuid

from dotenv import dotenv_values
from ontara_agent.clients import BackendClient, BrowserClient
from ontara_agent.mapping import approved_facts, validate_values


async def calibrate(args):
    if not args.seeded_demo_calibration:
        raise ValueError("Explicit --seeded-demo-calibration acknowledgement is required")
    backend, browser = BackendClient.from_env(), BrowserClient.from_env()
    try:
        body = Path(args.mapping).read_bytes()
        mapping = json.loads(body)
        if not isinstance(mapping, dict) or not mapping or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items()):
            raise ValueError("Mapping file must contain fieldName to approvedFactId pairs")
        worker_id = f"manual-calibration-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        envelope = await backend.lease(worker_id, args.job_id, args.case_id)
        if not envelope.get("job"):
            raise ValueError("No runnable, explicitly approved synthetic update")
        job, op, case = envelope["job"], envelope["operation"], envelope["case"]
        if op["action"] != "update" or op["portalId"] not in {"roads", "graffiti"} or job.get("readOnly"):
            raise ValueError("Calibration accepts an approved controlled-demo update only")
        if job.get("faultAfterAcceptance"):
            raise ValueError("A crash fault cannot be armed on a manual calibration")
        attempt_id = f"calibration-{uuid.uuid4().hex}"
        ctx = {"caseId": case["id"], "operationId": op["id"], "runId": op["runId"], "attemptId": attempt_id, "portalId": op["portalId"], "clientReference": op["clientReference"], "payloadDigest": op["payloadDigest"], "action": "update", "ticketId": op["externalTicketId"], "updateUrl": op["updateUrl"]}
        if op["state"] != "prepared":
            if op["state"] != "reconciling":
                await backend.transition(job, op, "reconciling", attempt_id=attempt_id, evidence={"kind": "manual_seeded_demo_calibration", "reason": "reconcile_unresolved_calibration"})
            result = await browser.call("reconcile", ctx)
            if not result.get("accepted") or not result.get("receipt"):
                raise ValueError("Calibration outcome is unresolved; no repeat write is allowed")
        else:
            result = await browser.call("inspect", ctx)
            observation = result.get("observation")
            if result.get("status") != "observed" or not observation:
                raise ValueError("The current receiving form is unavailable")
            facts = approved_facts(op["payload"])
            if any(fact_id not in facts for fact_id in mapping.values()):
                raise ValueError("Calibration mapping names an unapproved fact")
            values = {name: facts[fact_id] for name, fact_id in mapping.items()}
            validate_values(observation, values)
            evidence = {"kind": "manual_seeded_demo_calibration", "knowledgeKind": "seeded_demo", "disclosure": "Developer supplied this generic mapping for a synthetic event-day calibration; this action was not memory-guided runtime adaptation.", "mappingFileSha256": hashlib.sha256(body).hexdigest(), "mapping": mapping, "formFingerprint": observation["fingerprint"], "formVersion": observation["formVersion"], "processId": os.getpid()}
            await backend.event(case["id"], "manual_seeded_demo_calibration", "Running an explicitly labelled manual seeded-demo calibration with approved synthetic facts.", op=op, attempt_id=attempt_id, data=evidence)
            await backend.heartbeat(job)
            await backend.transition(job, op, "dispatch_started", attempt_id=attempt_id, evidence=evidence)
            result = await browser.call("submit", ctx | {"formFingerprint": observation["fingerprint"], "values": values, "returnReceipt": True})
            if not result.get("accepted") or not result.get("receipt"):
                await backend.transition(job, op, "outcome_unknown", attempt_id=attempt_id, evidence={"kind": "manual_seeded_demo_calibration", "reason": "receiving_acknowledgement_unverified"})
                raise ValueError("Calibration outcome is unverified; reconcile before any retry")
        await backend.receipt(job, op, result["receipt"], attempt_id)
        return {"status": "receipt_verified", "knowledgeKind": "seeded_demo", "operationId": op["id"], "caseId": case["id"], "runId": op["runId"], "ticketId": result["receipt"]["ticketId"], "receiptId": result["receipt"]["receiptId"], "formVersion": result["receipt"].get("formVersion"), "sameTicket": result["receipt"]["ticketId"] == op["externalTicketId"]}
    finally:
        await backend.close()
        await browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--case-id")
    parser.add_argument("--seeded-demo-calibration", action="store_true")
    parser.add_argument("--private-env", action="append", default=[])
    args = parser.parse_args()
    for filename in args.private_env:
        for key, value in dotenv_values(filename).items():
            if value is not None:
                os.environ.setdefault(key, value)
    try:
        result = asyncio.run(calibrate(args))
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({"status": "failed", "errorType": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
