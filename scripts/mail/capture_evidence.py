#!/usr/bin/env python3
"""Save sanitized actual mail/restart/dedup evidence for an existing synthetic case."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pymongo.errors import PyMongoError

from app.config import Settings
from app.mail import create_mail_service
from app.mail.config import MailSettings, read_env_file
from app.mail.store import utcnow
from app.service import CaseService
from app.storage import ArtifactStore, Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mail-env", default="/Users/ivan/.config/ontara/agentmail.env")
    parser.add_argument("--database-env", default="/Users/ivan/.config/ontara/mongodb.env")
    args = parser.parse_args()
    store = Store.connect(Settings.load(args.database_env))
    cases = CaseService(store, Settings.load(args.database_env))
    case = cases.get_case_internal(args.case_id)
    if not case.get("route", {}).get("demo"):
        raise SystemExit("Evidence capture is limited to existing labelled synthetic demo cases")
    settings = MailSettings.from_env(read_env_file(args.mail_env))
    service = create_mail_service(store.db, cases, ArtifactStore(store.db), settings)
    db = store.db
    query = {"caseId": args.case_id}
    def counts() -> dict:
        return {"outbox": db.outbox.count_documents({**query, "kind": "email"}),
                "inspectionJobs": db.jobs.count_documents({**query, "kind": "follow_up_inspection"}),
                "updateOperations": db.operations.count_documents({**query, "action": "update"})}
    before = counts()
    poll = service.poll_once(full_catchup=True)
    after = counts()
    mail = []
    genuine_source_ids = []
    for row in db.outbox.find({**query, "kind": "email"}).sort("purpose", 1):
        receiving = row.get("receivingEvidence", {})
        mail.append({"outboxId": row["id"], "purpose": row["purpose"], "operationId": row["operationId"],
                     "senderInboxId": row["senderInboxId"], "recipientInboxIds": row["recipients"],
                     "state": row["state"], "deliveryState": row.get("deliveryState"), "attemptCount": row.get("attemptCount"),
                     "providerMessageId": row.get("providerMessageId"), "sourceThreadId": row.get("providerThreadId"),
                     "receivingInboxId": receiving.get("inboxId"), "receivingThreadId": receiving.get("providerThreadId"),
                     "receivingEvidence": receiving.get("evidence")})
        if row["purpose"] == "AUTHORITY_QUESTION":
            for event in db.mail_events.find({**query, "outboxId": row["id"], "kind": "mail_received", "processingState": "PROCESSED"}):
                genuine_source_ids.append(event["_id"])
    genuine_jobs = [{"id": row["id"], "state": row["state"], "readOnly": row.get("readOnly"),
                     "inspectionStatus": row.get("inspectionStatus"), "sourceEventId": row.get("sourceEventId")}
                    for row in db.jobs.find({**query, "kind": "follow_up_inspection", "sourceEventId": {"$in": genuine_source_ids}})]
    receipts = [{"operationId": row["id"], "action": row["action"], "state": row["state"],
                 "ticketId": row["receipt"]["ticketId"], "receiptId": row["receipt"]["receiptId"]}
                for row in db.operations.find({**query, "state": "receipt_verified"})]
    result = {"schemaVersion": "1.0", "capturedAtUtc": utcnow().isoformat(), "environment": "development-integration",
              "controlledDemo": True, "caseId": args.case_id, "caseCancelledAtCapture": bool(case.get("cancelledAt")), "sanitization": {
                  "messageBodiesIncluded": False, "capabilityOrSessionUrlsIncluded": False, "tokensIncluded": False},
              "portalReceipts": receipts, "sameTicketAcrossReceipts": len({r["ticketId"] for r in receipts}) == 1,
              "mail": mail, "actualMessageCopiesStored": db.mail_messages.count_documents(query),
              "actualMessageCopiesWithTextStored": db.mail_messages.count_documents({**query, "text": {"$type": "string", "$ne": ""}}),
              "genuineMailInspectionJobs": genuine_jobs,
              "separateInspectionJobCount": after["inspectionJobs"] - len(genuine_jobs),
              "separateInspectionExplanation": "Separate inspection records are excluded from the genuine mail-source count.",
              "restartDedup": {"freshMailServiceProcessId": os.getpid(), "pollScope": "configured controlled inboxes",
                               "fullProviderCatchup": True, "countsBefore": before, "countsAfter": after,
                               "noAdditionalOutboxInspectionOrUpdate": before == after, "pollResults": poll},
              "claims": {"providerAcceptanceIsMunicipalAcceptance": False, "issueRepairVerified": False}}
    output = Path(__file__).resolve().parent / "evidence" / f"{args.case_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"evidenceFile": str(output), "mailMessages": len(mail), "actualCopies": result["actualMessageCopiesStored"],
                      "genuineMailInspectionJobs": len(genuine_jobs), "dedupCountsUnchanged": before == after}))
    service.close()
    db.client.close()


if __name__ == "__main__":
    try:
        main()
    except PyMongoError as error:
        raise SystemExit(f"Atlas operation failed ({type(error).__name__}); private diagnostic omitted.") from None
