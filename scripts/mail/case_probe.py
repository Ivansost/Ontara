#!/usr/bin/env python3
"""Verify real mail for an existing case with real persisted portal receipts.

This creates no case, receipt, approval, portal update, or fabricated authority event.
The configured mail service may send its existing receipt-authorized controlled mail.
"""

from __future__ import annotations

import argparse
import json
import time

from pymongo.errors import PyMongoError

from app.config import Settings
from app.mail import create_mail_service
from app.mail.config import MailSettings, read_env_file
from app.mail.provider import ProviderFailure
from app.service import CaseService
from app.storage import ArtifactStore, Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mail-env", default="/Users/ivan/.config/ontara/agentmail.env")
    parser.add_argument("--database-env", default="/Users/ivan/.config/ontara/mongodb.env")
    parser.add_argument("--wait-seconds", type=int, default=35)
    args = parser.parse_args()
    settings = Settings.load(args.database_env)
    store = Store.connect(settings)
    cases = CaseService(store, settings)
    cases.get_case_internal(args.case_id)
    mail = create_mail_service(store.db, cases, ArtifactStore(store.db),
                               MailSettings.from_env(read_env_file(args.mail_env)))
    operations = list(store.db.operations.find({"caseId": args.case_id, "state": "receipt_verified"}))
    if not operations:
        raise SystemExit("This case has no saved verified portal operation; no email was scheduled.")
    for operation in operations:
        mail.on_receipt_verified(args.case_id, operation, operation["receipt"])
    deadline = time.monotonic() + min(50, max(1, args.wait_seconds))
    while True:
        mail.process_outbox_once()
        mail.poll_once()
        summary = mail.status(args.case_id)
        if summary["outbox"] and all(item.get("deliveryState") == "RECEIVED" for item in summary["outbox"]):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(2)
    before = store.db.jobs.count_documents({"caseId": args.case_id, "kind": "follow_up_inspection"})
    duplicate_result = mail.poll_once(full_catchup=True)
    after = store.db.jobs.count_documents({"caseId": args.case_id, "kind": "follow_up_inspection"})
    summary = mail.status(args.case_id)
    print(json.dumps({"caseId": args.case_id, "mail": summary,
                      "inspectionJobsBeforeDuplicatePoll": before,
                      "inspectionJobsAfterDuplicatePoll": after,
                      "duplicatePollCreatedNoAdditionalInspection": before == after,
                      "duplicatePoll": duplicate_result}, default=str))
    mail.close()
    store.db.client.close()


if __name__ == "__main__":
    try:
        main()
    except PyMongoError as error:
        raise SystemExit(f"Atlas operation failed ({type(error).__name__}); no credential-bearing diagnostic printed.") from None
    except ProviderFailure as error:
        raise SystemExit(f"AgentMail operation failed ({error.code}).") from None
