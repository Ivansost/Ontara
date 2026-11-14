#!/usr/bin/env python3
"""GET-only observation of ONE existing scripted-email demo case.

Never creates/approves a report, polls mail, sends email, or retries an action.
Repeat with the same case ID to resume observation. Uses the Python standard library.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PURPOSES = ("RESIDENT_SCRIPTED_SUBMITTED", "RESIDENT_SCRIPTED_RESOLVED")


def private_config(path: str) -> dict[str, str]:
    file = Path(path).expanduser()
    metadata = file.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise ValueError("Use an owner-only regular cloud configuration file")
    values = {}
    for line in file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def api_origin(value: str) -> str:
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    render = bool(parsed.hostname and parsed.hostname.endswith(".onrender.com"))
    if (parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or any(char.isspace() for char in value)
            or not (local and parsed.scheme in {"http", "https"} or render and parsed.scheme == "https")):
        raise ValueError("Use the configured HTTPS Render API origin or loopback development origin")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_json(origin: str, token: str, path: str) -> dict:
    try:
        request = Request(origin + path, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            value = json.loads(response.read(512 * 1024))
    except HTTPError as error:
        raise ValueError(f"Read-only observation returned HTTP {error.code}; private response omitted") from None
    except (URLError, OSError, ValueError):
        raise ValueError("Read-only observation is unavailable; rerun for the same case without approving again") from None
    if not isinstance(value, dict):
        raise ValueError("The API returned an invalid read-only observation")
    return value


def timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError:
        return None


def collect(case_id: str, get) -> dict:
    if not re.fullmatch(r"case_[a-f0-9]{32}", case_id):
        raise ValueError("Use the existing case identifier saved by the reporting session")
    case = get("/internal/v1/cases/" + case_id)
    operation_id = case.get("currentOperationId")
    if not case.get("scriptedEmailDemo") or not isinstance(operation_id, str) or not re.fullmatch(r"op_[a-f0-9]{32}", operation_id):
        raise ValueError("This existing case is not an approved scripted presentation case")
    operation = get("/internal/v1/operations/" + operation_id)
    metadata = operation.get("scriptedEmailDemo") or {}
    if operation.get("caseId") != case_id or metadata.get("enabled") is not True or metadata.get("simulated") is not True:
        raise ValueError("The selected case does not match a captured scripted approval")
    mail = get("/internal/v1/mail/status?" + urlencode({"case_id": case_id}))
    outbox = mail.get("outbox", [])
    recipient = (case.get("notifications") or {}).get("email", "").lower()
    rows = []
    for purpose in PURPOSES:
        found = [item for item in outbox if item.get("purpose") == purpose]
        item = found[0] if len(found) == 1 else {}
        evidence = item.get("receivingEvidence") or {}
        rows.append({"purpose": purpose, "matchingOutboxCount": len(found), "state": item.get("state"),
            "deliveryState": item.get("deliveryState"), "attemptCount": item.get("attemptCount"),
            "dueAt": item.get("scriptedDueAt"), "sentAt": item.get("sentAt"), "sentEvidence": item.get("sentEvidence"),
            "receivingObservedAt": item.get("receivedAt") or evidence.get("observedAt"),
            "receivingEvidenceVerified": bool(item.get("deliveryState") == "RECEIVED" and evidence.get("evidence") == "message_read_from_controlled_receiving_inbox"
                and evidence.get("providerMessageId") == item.get("providerMessageId") and evidence.get("providerThreadId")),
            "approvedRecipientMatches": bool(recipient and evidence.get("inboxId", "").lower() == recipient)})
    approved_at, first_sent, second_sent = timestamp(metadata.get("approvedAt")), timestamp(rows[0]["sentAt"]), timestamp(rows[1]["sentAt"])
    first_delay = (first_sent - approved_at).total_seconds() if first_sent and approved_at else None
    second_delay = (second_sent - first_sent).total_seconds() if first_sent and second_sent else None
    timing_pass = first_delay is not None and first_delay >= 5 and second_delay is not None and second_delay >= 5
    exact_two = len(outbox) == 2 and all(row["matchingOutboxCount"] == 1 for row in rows)
    received = all(row["state"] == "SENT" and row["deliveryState"] == "RECEIVED" and row["attemptCount"] == 1
        and row["receivingEvidenceVerified"] and row["approvedRecipientMatches"] for row in rows)
    actual_status_separate = case.get("stage") != "resolved_in_demo" and not case.get("demoResolution")
    return {"scenario": "scripted_two_email_presentation", "observedAt": datetime.now(timezone.utc).isoformat(),
        "caseId": case_id, "approvedAt": metadata.get("approvedAt"), "notifications": rows,
        "timing": {"firstSentAfterApprovalSeconds": first_delay, "secondSentAfterFirstSentSeconds": second_delay, "bothMinimumFiveSeconds": timing_pass},
        "exactlyTwoOutboxItems": exact_two, "actualCaseStage": case.get("stage"), "actualReceiptPresent": bool(case.get("receipt")),
        "noTimerDerivedResolutionRecord": actual_status_separate, "qualified": bool(exact_two and received and timing_pass and actual_status_separate),
        "limits": {"cityUpdatesAreScripted": True, "controlledRecipientObservationOnly": True, "physicalRepairVerified": False,
            "receivingTimestampIsObservationTime": True},
        "sanitization": {"addressesIncluded": False, "messageBodiesIncluded": False, "receivingCapabilitiesIncluded": False,
            "rawRunOperationDigestTupleIncluded": False}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--cloud-env", default="/Users/ivan/.config/ontara/cloud.env")
    parser.add_argument("--output", required=True)
    parser.add_argument("--wait-seconds", type=int, default=40)
    args = parser.parse_args()
    config = private_config(args.cloud_env)
    origin, token = api_origin(config.get("BACKEND_BASE_URL", "")), config.get("ONTARA_INTERNAL_TOKEN")
    if not token:
        raise ValueError("The existing private API credential is required")
    deadline = time.monotonic() + min(120, max(0, args.wait_seconds))
    while True:
        result = collect(args.case_id, lambda path: get_json(origin, token, path))
        if result["qualified"] or time.monotonic() >= deadline:
            break
        time.sleep(1)
    destination = Path(args.output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"qualified": result["qualified"], "output": str(destination), "exactlyTwoOutboxItems": result["exactlyTwoOutboxItems"], "timing": result["timing"]}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError):
        raise SystemExit("Scripted email observation is incomplete. Resume the same case; no report or email was retried. Private diagnostics omitted.") from None
