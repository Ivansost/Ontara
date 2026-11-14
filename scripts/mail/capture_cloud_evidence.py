#!/usr/bin/env python3
"""Append sanitized hosted-mail observations using authenticated GET requests only.

This observer never sends mail, polls a provider, creates/approves a case, releases
a hold, dispatches work or touches a local application runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.mail.config import read_env_file
from trigger_followup import validate_origin


def pick(value: dict | None, keys: tuple[str, ...]) -> dict:
    value = value or {}
    return {key: value[key] for key in keys if key in value}


def public_artifact(artifact: dict) -> dict:
    """Replace receiving lookup components with aliases and exact-match booleans."""
    result = json.loads(json.dumps(artifact))
    for observation in result.get("observations", []):
        case = observation["case"]
        run_id = case.pop("runId", None)
        operations = observation.get("operations", [])
        aliases = {op["id"]: f"{op.get('action', 'operation')}-v{op.get('caseVersion', 'unknown')}" for op in operations}
        current = case.pop("currentOperationId", None)
        case["currentOperationAlias"] = aliases.get(current) if current else None
        case["hasRunId"] = bool(run_id)
        def receipt(value: dict, operation_id: str | None = None) -> None:
            recorded_run = value.pop("runId", None)
            reference = value.pop("clientReference", None)
            if recorded_run is not None:
                value["runMatchesCase"] = recorded_run == run_id
            if reference is not None:
                value["clientReferenceMatchesOperation"] = reference == operation_id
        receipt(case.get("receipt") or {}, current)
        for op in operations:
            operation_id = op.pop("id")
            op["operationAlias"] = aliases[operation_id]
            op["runMatchesCase"] = op.pop("runId", None) == run_id
            receipt(op.get("receipt") or {}, operation_id)
        for message in observation.get("mail", {}).get("outbox", []):
            message["operationAlias"] = aliases.get(message.pop("operationId", None), "unmatched-operation")
        confirmation = observation.get("hold", {}).get("portalConfirmation") or {}
        if confirmation:
            confirmation["runMatchesCase"] = confirmation.pop("runId", None) == run_id
            confirmation["hasSnapshotDigest"] = bool(confirmation.pop("snapshotDigest", None))
        for event in observation.get("executionEvents", []):
            event["operationAlias"] = aliases.get(event.pop("operationId", None), "unmatched-operation")
            data = event.get("data") or {}
            if "runId" in data:
                data["runMatchesCase"] = data.pop("runId") == run_id
            if isinstance(data.get("jobId"), str) and data["jobId"].startswith("job_op_"):
                data["jobAlias"] = aliases.get(data.pop("jobId")[4:], "execution-job")
        observation.pop("_privateReceivingLookups", None)
    result["sanitization"].update({"rawReceivingRunIdsIncluded": False, "rawOperationReferencesIncluded": False,
                                    "payloadDigestsIncluded": False, "comparisonsComputedBeforeRedaction": True})
    return result


def observe(client: httpx.Client, case_id: str, label: str) -> dict:
    def get(path: str, **kwargs) -> dict:
        response = client.get(path, **kwargs)
        if response.status_code != 200:
            raise ValueError(f"Read-only hosted observation returned HTTP {response.status_code}; body omitted")
        return response.json()
    case = get(f"/internal/v1/cases/{case_id}")
    if (case.get("route") or {}).get("demo") is not True or (case.get("route") or {}).get("id") != "halton-roads-demo":
        raise ValueError("Read-only capture requires an existing labelled synthetic Roads case")
    hold = get(f"/internal/v1/cases/{case_id}/follow-up-hold")
    mail = get("/internal/v1/mail/status", params={"case_id": case_id})
    evidence = get(f"/internal/v1/cases/{case_id}/evidence")
    receipt_keys = ("ticketId", "receiptId", "portalId", "action", "runId", "clientReference")
    operations = []
    private_lookups = []
    for operation in evidence.get("operations", []):
        item = pick(operation, ("id", "action", "state", "caseVersion", "runId"))
        item["receipt"] = pick(operation.get("receipt"), receipt_keys)
        item["exactReceiptMatch"] = {
            "caseMatches": operation.get("caseId") == case_id,
            "runMatchesCase": operation.get("runId") == case.get("runId"),
            "clientReferenceMatchesOperation": (operation.get("receipt") or {}).get("clientReference") == operation.get("id"),
            "payloadDigestMatches": bool((operation.get("receipt") or {}).get("payloadDigest")) and
                                    (operation.get("receipt") or {}).get("payloadDigest") == operation.get("payloadDigest")}
        operations.append(item)
        private_lookups.append(pick(operation, ("id", "runId", "payloadDigest")))
    outbox = []
    for message in mail.get("outbox", []):
        item = pick(message, ("id", "caseId", "operationId", "purpose", "state", "deliveryState", "attemptCount",
                              "holdReason", "providerMessageId", "providerThreadId", "updatedAt"))
        item["receivingEvidence"] = pick(message.get("receivingEvidence"),
            ("inboxId", "providerMessageId", "providerThreadId", "observedAt", "evidence"))
        outbox.append(item)
    control = pick(hold, ("caseId", "held", "heldAt", "releasedAt", "nextCreateFaultArmed"))
    control["authorityOutbox"] = pick(hold.get("authorityOutbox"), ("id", "state", "attemptCount"))
    control["portalConfirmation"] = pick(hold.get("portalConfirmation"),
        ("runId", "portalId", "action", "formVersion", "snapshotDigest", "verifiedAt"))
    events = []
    for event in evidence.get("events", []):
        if event.get("kind") not in {"worker_leased", "worker_process_exited", "dispatch_started", "outcome_unknown",
                                     "reconciling", "receipt_verified", "form_inspected", "execution_mapping_validated",
                                     "diagnostic_inspection_requested"}:
            continue
        item = pick(event, ("id", "kind", "operationId", "createdAt"))
        # Never retain raw tool/model inputs/results, narrative text, messages or URLs.
        item["data"] = pick(event.get("data"), ("runId", "attemptId", "processId", "exitCode", "attempt", "fence",
                                                "inspectionStatus", "jobId", "sourceEventId", "faultAfterAcceptance",
                                                "inspectionJobId", "diagnostic"))
        events.append(item)
    initial = next((op for op in operations if op.get("action") == "create" and op.get("state") == "receipt_verified"), None)
    authority = [m for m in outbox if m.get("purpose") == "AUTHORITY_QUESTION"]
    held_receipt_zero = bool(initial and hold.get("held") is True and len(authority) == 1
        and authority[0].get("operationId") == initial["id"] and authority[0].get("state") == "HELD"
        and authority[0].get("attemptCount") == 0 and not authority[0].get("providerMessageId")
        and mail.get("messagesStored") == 0 and not case.get("pendingQuestions")
        and (case.get("receipt") or {}).get("receiptId") == initial["receipt"].get("receiptId"))
    return {"label": label, "observedAtUtc": datetime.now(timezone.utc).isoformat(),
            "case": {**pick(case, ("id", "runId", "version", "stage", "approvedVersion", "currentOperationId")),
                     "cancelled": bool(case.get("cancelledAt")), "receipt": pick(case.get("receipt"), receipt_keys),
                     "pendingQuestionIds": [q["id"] for q in case.get("pendingQuestions", [])]},
            "hold": control, "mail": {"enabled": mail.get("enabled"), "workerRunning": mail.get("workerRunning"),
                                     "messagesStored": mail.get("messagesStored"), "outbox": outbox},
            "operations": operations, "executionEvents": events, "_privateReceivingLookups": private_lookups,
            "barriers": {"verifiedInitialReceiptWithHeldZeroAttempts": held_receipt_zero},
            "counts": {"outbox": len(outbox), "updateOperations": sum(o.get("action") == "update" for o in operations)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--runtime-env", default="/Users/ivan/.config/ontara/runtime.env")
    args = parser.parse_args()
    origin = validate_origin(args.api_url)
    if not re.fullmatch(r"case_[a-f0-9]{32}", args.case_id) or not re.fullmatch(r"[a-z0-9_-]{1,60}", args.label):
        raise ValueError("Use an existing case ID and a short observation label")
    private = read_env_file(args.runtime_env) if args.runtime_env and Path(args.runtime_env).is_file() else {}
    token = os.environ.get("ONTARA_INTERNAL_TOKEN") or private.get("ONTARA_INTERNAL_TOKEN")
    if not token:
        raise ValueError("Private ONTARA_INTERNAL_TOKEN is required")
    with httpx.Client(base_url=origin, headers={"Authorization": "Bearer " + token}, timeout=40, follow_redirects=False) as client:
        observation = observe(client, args.case_id, args.label)
    if args.label in {"receipt_held_before_restart", "receipt_held_after_restart", "negative_memory_held"}:
        if not observation["barriers"]["verifiedInitialReceiptWithHeldZeroAttempts"]:
            raise ValueError("The verified initial receipt plus HELD/zero-attempt barrier is not yet present; no observation appended")
    path = Path(__file__).resolve().parent / "evidence" / f"cloud-{args.case_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    private_dir = Path.home() / ".config" / "ontara" / "evidence"
    private_dir.mkdir(parents=True, exist_ok=True)
    private_dir.chmod(0o700)
    private_path = private_dir / path.name
    artifact = json.loads(private_path.read_text()) if private_path.is_file() else (json.loads(path.read_text()) if path.is_file() else {
        "schemaVersion": "1.0", "environment": "hosted-render", "caseId": args.case_id,
        "observerRequests": "authenticated GET only", "controlledDemo": True,
        "sanitization": {"messageBodiesIncluded": False, "capabilityOrSessionUrlsIncluded": False, "tokensIncluded": False},
        "hostedMailServiceRestartVerified": False, "observations": []})
    artifact["observations"].append(observation)
    private_path.write_text(json.dumps(artifact, indent=2) + "\n")
    private_path.chmod(0o600)
    serialized = json.dumps(public_artifact(artifact), indent=2) + "\n"
    if "http://" in serialized or "https://" in serialized or "Bearer " in serialized:
        raise ValueError("Sanitization refused an artifact containing a URL or Bearer credential")
    if re.search(r'"(?:op_|run_)[a-f0-9]{32}"', serialized) or '"payloadDigest":' in serialized or '"clientReference":' in serialized:
        raise ValueError("Sanitization refused a raw receiving lookup component")
    path.write_text(serialized)
    print(json.dumps({"evidenceFile": str(path), "label": args.label, "held": observation["hold"].get("held"),
                      "caseStage": observation["case"].get("stage"), "counts": observation["counts"],
                      "outboxStates": [{"purpose": m.get("purpose"), "state": m.get("state"),
                                        "deliveryState": m.get("deliveryState"), "attemptCount": m.get("attemptCount")}
                                       for m in observation["mail"]["outbox"]]}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, httpx.HTTPError) as error:
        raise SystemExit(str(error) if isinstance(error, ValueError) else type(error).__name__) from None
