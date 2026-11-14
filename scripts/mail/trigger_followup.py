#!/usr/bin/env python3
"""Poll genuine controlled mail for an EXISTING verified synthetic Roads case.

Uses internal Bearer auth, never creates cases/receipts/approvals or dispatches a portal
write. The server's idempotent receipt hook/outbox supplies the genuine authority mail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.mail.config import read_env_file


def validate_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Use an API origin without credentials, paths, query or fragment")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    render = bool(parsed.hostname and parsed.hostname.endswith(".onrender.com"))
    if not ((local and parsed.scheme in {"http", "https"}) or (render and parsed.scheme == "https")):
        raise ValueError("This demo helper accepts HTTPS Render origins or a loopback development origin")
    return origin.rstrip("/")


def request_json(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    response = client.request(method, path, **kwargs)
    if response.status_code >= 300:
        raise ValueError(f"Authenticated API operation returned HTTP {response.status_code}; response body omitted")
    return response.json()


def verify_existing_case(client: httpx.Client, case_id: str) -> None:
    case = request_json(client, "GET", f"/internal/v1/cases/{case_id}")
    route = case.get("route") or {}
    if route.get("demo") is not True or route.get("id") != "halton-roads-demo" or case.get("cancelledAt"):
        raise ValueError("Follow-up requires an uncancelled labelled synthetic Roads case")
    if not (case.get("receipt") or {}).get("ticketId") or not case.get("currentOperationId"):
        raise ValueError("An existing verified portal receipt is required; no email was triggered")
    operation = request_json(client, "GET", "/internal/v1/operations/" + case["currentOperationId"])
    receipt = operation.get("receipt") or {}
    if operation.get("caseId") != case_id or operation.get("state") != "receipt_verified" or receipt.get("ticketId") != case["receipt"]["ticketId"]:
        raise ValueError("The saved operation does not have a matching verified receipt; no email was triggered")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--runtime-env", default="/Users/ivan/.config/ontara/runtime.env")
    parser.add_argument("--wait-seconds", type=int, default=35)
    args = parser.parse_args()
    origin = validate_origin(args.api_url)
    if not re.fullmatch(r"case_[a-f0-9]{32}", args.case_id):
        raise SystemExit("Use an existing case identifier from the resident case page")
    private = read_env_file(args.runtime_env) if args.runtime_env and Path(args.runtime_env).is_file() else {}
    token = os.environ.get("ONTARA_INTERNAL_TOKEN") or private.get("ONTARA_INTERNAL_TOKEN")
    if not token:
        raise SystemExit("ONTARA_INTERNAL_TOKEN must be provided privately; it is never accepted on the command line")
    with httpx.Client(base_url=origin, headers={"Authorization": "Bearer " + token}, timeout=30, follow_redirects=False) as client:
        verify_existing_case(client, args.case_id)
        deadline = time.monotonic() + min(50, max(1, args.wait_seconds))
        while True:
            # This invokes only the server's durable mail replay/send/poll loop. It neither
            # leases the read-only inspection job nor dispatches an approved portal update.
            request_json(client, "POST", "/internal/v1/mail/poll")
            status = request_json(client, "GET", "/internal/v1/mail/status", params={"case_id": args.case_id})
            authority = [m for m in status.get("outbox", []) if m.get("purpose") == "AUTHORITY_QUESTION"]
            if authority and authority[0].get("deliveryState") == "RECEIVED":
                print(json.dumps({"caseId": args.case_id, "controlledDemo": True, "purpose": "AUTHORITY_QUESTION",
                                  "state": authority[0]["state"], "deliveryState": "RECEIVED",
                                  "outboxId": authority[0]["id"], "providerMessageId": authority[0].get("providerMessageId"),
                                  "nextStep": "The existing executor inspects the current form before the UI asks the missing authored question."}))
                return
            if time.monotonic() >= deadline:
                raise SystemExit("Mail remains pending in the durable outbox; rerun this command safely. No receipt or approval was fabricated.")
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, httpx.HTTPError) as error:
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        raise SystemExit(detail) from None
