#!/usr/bin/env python3
"""Exercise real Atlas case transactions without making an external portal write."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8001")
parser.add_argument("--runtime-env", default="~/.config/ontara/runtime.env")
parser.add_argument("--output", required=True)
args = parser.parse_args()
private = dotenv_values(Path(args.runtime_env).expanduser())
token = private.get("ONTARA_INTERNAL_TOKEN")
if not token:
    raise SystemExit("Internal authentication is not configured")
internal_headers = {"Authorization": f"Bearer {token}"}
payload = {"issueId": "roads-pothole", "location": {"municipalityId": "milton-town", "upperTierId": "halton-region",
    "fixtureId": "halton-regional-road", "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True,
    "reporterMunicipalityId": "toronto-city"}, "answers": {"immediateDanger": "No", "roadPosition": "At curb", "travelDirection": "Northbound",
    "description": "Synthetic backend transaction verification pothole. No external submission requested by this test."}}
proof = {"checkedAt": datetime.now(timezone.utc).isoformat(), "scope": "Real Atlas HTTP case ledger; no external portal write", "checks": {}}
case_id = None
with httpx.Client(base_url=args.base_url, timeout=60) as client:
    try:
        preview = client.post("/v1/routes/preview", json=payload)
        preview.raise_for_status()
        route = preview.json()["route"]
        assert route["knowledgeStatus"] == "ready" and route["retrievalEvidence"]["queryExecuted"] is True
        proof["nativeProcedure"] = route["publishedProcedure"]
        proof["nativeIndex"] = {k: route["retrievalEvidence"].get(k) for k in ("indexName", "model", "queryText", "nativeQuery", "queryExecuted")}
        proof["checks"]["nativeProcedureBeforeApproval"] = True
        created = client.post("/v1/cases", json=payload)
        assert created.status_code == 201, created.status_code
        case = created.json()
        case_id = case["id"]
        proof["caseId"] = case_id
        proof["runId"] = case["runId"]
        proof["checks"]["incidentOverridesResidence"] = case["route"]["authorityId"] == "halton-region"
        with httpx.Client(base_url=args.base_url) as outsider:
            proof["checks"]["crossSessionDenied"] = outsider.get(f"/v1/cases/{case_id}").status_code == 404
        approved = client.post(f"/v1/cases/{case_id}/approve", json={"version": 1})
        approved.raise_for_status()
        op1 = approved.json()["currentOperationId"]
        repeated = client.post(f"/v1/cases/{case_id}/approve", json={"version": 1})
        proof["checks"]["duplicateApprovalSameOperation"] = repeated.json()["currentOperationId"] == op1
        changed = {**payload["answers"], "description": "Edited synthetic transaction verification. This test still makes no external submission."}
        edited = client.patch(f"/v1/cases/{case_id}", json={"expectedVersion": 1, "answers": changed})
        edited.raise_for_status()
        proof["checks"]["materialEditInvalidatesApproval"] = edited.json()["version"] == 2 and edited.json()["approvedVersion"] is None
        proof["checks"]["staleApprovalRejected"] = client.post(f"/v1/cases/{case_id}/approve", json={"version": 1}).status_code == 409
        old = client.get(f"/internal/v1/cases/{case_id}/versions/1", headers=internal_headers)
        old.raise_for_status()
        proof["checks"]["originalVersionPreserved"] = old.json()["payload"]["answers"]["description"] == payload["answers"]["description"]
        approved2 = client.post(f"/v1/cases/{case_id}/approve", json={"version": 2})
        approved2.raise_for_status()
        proof["checks"]["newVersionNewOperation"] = approved2.json()["currentOperationId"] != op1
        lease = client.post("/internal/v1/jobs/lease", headers=internal_headers, json={"workerId": "backend-live-ledger-verifier", "caseId": case_id, "leaseSeconds": 30})
        lease.raise_for_status()
        job = lease.json()["job"]
        assert job and job["fence"] == 1
        proof["checks"]["durableJobLease"] = True
        guard = {"workerId": job["workerId"], "leaseToken": job["leaseToken"]}
        cancelled = client.post(f"/v1/cases/{case_id}/cancel", json={"reason": "Completed synthetic backend verification; no external write was dispatched."})
        cancelled.raise_for_status()
        proof["checks"]["cancelledLeaseRejected"] = client.post(f"/internal/v1/jobs/{job['id']}/heartbeat", headers=internal_headers, json=guard).status_code == 409
        inactive = {**payload, "issueId": "waste-missed-collection"}
        proof["checks"]["inactiveServiceRejected"] = client.post("/v1/cases", json=inactive).status_code == 422
        proof["checks"]["internalUnauthenticatedRejected"] = client.get(f"/internal/v1/cases/{case_id}").status_code == 401
        assert all(proof["checks"].values()), proof["checks"]
        proof["passed"] = True
    finally:
        if case_id:
            client.post(f"/v1/cases/{case_id}/cancel", json={"reason": "Synthetic live backend verification complete."})
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
Path(args.output).write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps({"passed": proof["passed"], "checks": len(proof["checks"]), "caseId": proof["caseId"], "output": args.output}))
