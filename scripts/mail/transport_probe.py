#!/usr/bin/env python3
"""One idempotent real controlled transport probe, with durable Atlas evidence.

This proves mail transport only; it never creates a case or claims a municipal receipt.
Run from the repository root with PYTHONPATH=services/api. --send permits the first
send; reruns reconcile the exact provider message instead of sending again.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import timedelta

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.mail.config import MailSettings, read_env_file
from app.mail.provider import AgentMailProvider, ProviderFailure
from app.mail.store import MongoMailStore, stable_id, utcnow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--probe-id", default="ontara-2026-11-14-mail-transport-v1")
    parser.add_argument("--mail-env", default="/Users/ivan/.config/ontara/agentmail.env")
    parser.add_argument("--database-env", default="/Users/ivan/.config/ontara/mongodb.env")
    parser.add_argument("--wait-seconds", type=int, default=45)
    args = parser.parse_args()
    mail = MailSettings.from_env(read_env_file(args.mail_env))
    database = read_env_file(args.database_env)
    client = MongoClient(database["MONGODB_URI"], tz_aware=True, serverSelectionTimeoutMS=10000)
    db = client[database.get("MONGODB_DATABASE", "ontara")]
    store = MongoMailStore(db)
    store.ensure_indexes()
    provider = AgentMailProvider(mail.api_key)
    org = provider.organization()
    inboxes = {inbox["inbox_id"] for inbox in provider.list_inboxes()}
    if not set(mail.role_inboxes) <= inboxes or org.get("suspended_at"):
        raise SystemExit("Controlled role inboxes unavailable or account suspended")
    print(json.dumps({"inboxCount": org.get("inbox_count"), "inboxLimit": org.get("inbox_limit"),
                      "controlledRolesVerified": True}))
    probe_id = "probe_" + stable_id(args.probe_id)[:32]
    token = stable_id(probe_id, "correlation")[:32]
    existing = db.outbox.find_one({"_id": probe_id})
    if not existing:
        if not args.send:
            raise SystemExit("No existing probe. --send is required for the first controlled email.")
        today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sends = sum(1 for inbox in mail.role_inboxes for _ in provider.messages(inbox, after=today.isoformat(), labels=["sent"]))
        if sends >= mail.daily_send_budget:
            raise SystemExit("Conservative local free-send budget reached")
        now = utcnow()
        existing = {"_id": probe_id, "id": probe_id, "kind": "email_transport_probe", "provider": "agentmail",
                    "purpose": "CONTROLLED_TRANSPORT_PROBE", "senderInboxId": mail.authority_inbox_id,
                    "recipients": [mail.ontara_inbox_id], "correlationToken": token,
                    "subject": f"[Ontara DEMO {token}] Controlled mail transport verification",
                    "text": "SIMULATED AUTHORITY — transport verification only.\nPlease confirm the nearest landmark in the controlled demo UI when a verified case requests it.\nNo municipal report, acceptance or repair is claimed by this probe.\n" + f"Correlation: {token}\n",
                    "providerLabel": "ontara-" + token, "state": "QUEUED", "createdAt": now,
                    "updatedAt": now, "nextAttemptAt": now, "visibility": "restricted", "attemptCount": 0}
        existing["payloadDigest"] = stable_id(existing["subject"], existing["text"])
        store.enqueue(existing)
    mail.require_participants(existing["senderInboxId"], existing["recipients"])
    if existing["state"] == "QUEUED":
        if not args.send:
            raise SystemExit("The queued first send requires --send")
        claimed = db.outbox.find_one_and_update({"_id": probe_id, "state": "QUEUED"},
                                               {"$set": {"state": "SENDING", "updatedAt": utcnow()}, "$inc": {"attemptCount": 1}})
        if not claimed:
            raise SystemExit("Another process claimed this probe")
        store.event("probe-attempt:" + probe_id, {"kind": "mail_send_attempt", "outboxId": probe_id,
                                                  "purpose": "CONTROLLED_TRANSPORT_PROBE"})
        try:
            sent = provider.send(existing)
            db.outbox.update_one({"_id": probe_id}, {"$set": {"state": "SENT", "providerMessageId": sent["message_id"],
                                      "providerThreadId": sent["thread_id"], "updatedAt": utcnow()}})
        except ProviderFailure as error:
            db.outbox.update_one({"_id": probe_id}, {"$set": {"state": "OUTCOME_UNKNOWN", "lastError": error.code}})
            raise SystemExit("Probe send outcome unknown; rerun to reconcile. No automatic resend.") from None
    existing = db.outbox.find_one({"_id": probe_id})
    if existing["state"] in {"SENDING", "OUTCOME_UNKNOWN"}:
        candidates = list(provider.messages(mail.authority_inbox_id, labels=[existing["providerLabel"]]))
        matches = [m for m in candidates if m.get("subject") == existing["subject"]]
        if len(matches) != 1:
            raise SystemExit("Probe send still ambiguous; no resend performed")
        db.outbox.update_one({"_id": probe_id}, {"$set": {"state": "SENT", "providerMessageId": matches[0]["message_id"],
                                  "providerThreadId": matches[0]["thread_id"], "reconciled": True}})
        existing = db.outbox.find_one({"_id": probe_id})
    source = provider.get_message(mail.authority_inbox_id, existing["providerMessageId"])
    store.save_message(source, outbox_id=probe_id, direction="outgoing")
    deadline = time.monotonic() + min(args.wait_seconds, 55)
    receiving = None
    while time.monotonic() <= deadline:
        try:
            candidate = provider.get_message(mail.ontara_inbox_id, existing["providerMessageId"])
            if "received" in candidate.get("labels", []) and candidate.get("subject") == existing["subject"]:
                receiving = candidate
                break
        except ProviderFailure:
            pass
        time.sleep(2)
    if not receiving:
        raise SystemExit("Provider accepted the send; genuine receiving-inbox evidence is still pending. Rerun safely.")
    store.save_message(receiving, outbox_id=probe_id)
    evidence = {"inboxId": mail.ontara_inbox_id, "providerMessageId": receiving["message_id"],
                "providerThreadId": receiving["thread_id"], "evidence": "read_from_controlled_receiving_inbox",
                "observedAt": utcnow()}
    db.outbox.update_one({"_id": probe_id}, {"$set": {"deliveryState": "RECEIVED", "receivingEvidence": evidence}})
    store.event("probe-received:" + probe_id, {"kind": "mail_transport_probe_receipt", "outboxId": probe_id, **evidence})
    print(json.dumps({"probeId": probe_id, "state": "SENT", "deliveryState": "RECEIVED",
                      "providerMessageId": receiving["message_id"], "providerThreadId": receiving["thread_id"],
                      "sourceInboxId": mail.authority_inbox_id, "receivingInboxId": mail.ontara_inbox_id,
                      "atlasMessageCopies": store.messages.count_documents({"outboxId": probe_id}),
                      "attemptCount": db.outbox.find_one({"_id": probe_id})["attemptCount"]}))
    provider.close()
    client.close()


if __name__ == "__main__":
    try:
        main()
    except PyMongoError as error:
        raise SystemExit(f"Atlas operation failed ({type(error).__name__}); no credential-bearing diagnostic printed.") from None
    except ProviderFailure as error:
        raise SystemExit(f"AgentMail operation failed ({error.code}).") from None
