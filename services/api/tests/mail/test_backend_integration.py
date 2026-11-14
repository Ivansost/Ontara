"""Exercise the actual case-service contract; mail transport is a test double here."""
import mongomock

from app.config import Settings
from app.mail.service import MailService
from app.mail.store import MongoMailStore, utcnow
from app.models import ApprovalRequest, CaseCreate, LeaseRequest, OperationTransition, Receipt, ReceiptRecord
from app.service import CaseService
from app.storage import Store

from .test_mail import Provider, env


def test_real_backend_schedules_one_read_only_inspection_without_question(env):
    settings = env[-1]
    db = mongomock.MongoClient(tz_aware=True).ontara
    store = Store(db, transactions=False)
    store.ensure_indexes()
    cases = CaseService(store, Settings())
    case = cases.create_case("synthetic-test-session", CaseCreate(
        issueId="roads-pothole",
        location={"municipalityId": "milton-town", "upperTierId": "halton-region",
                  "fixtureId": "halton-regional-road", "incidentAddress": "Synthetic test regional road", "confirmed": True},
        answers={"immediateDanger": "No", "roadPosition": "In travel lane", "travelDirection": "Northbound",
                 "description": "A synthetic pothole for a test."},
    ))
    approved = cases.approve(case["id"], "synthetic-test-session", ApprovalRequest(version=1))
    lease = cases.lease_job(LeaseRequest(worker_id="test-executor", case_id=case["id"]))
    operation, job = lease["operation"], lease["job"]
    cases.transition(operation["id"], OperationTransition(
        worker_id="test-executor", lease_token=job["leaseToken"], job_id=job["id"], expected_state="prepared", state="dispatch_started"))
    receipt = Receipt(ticketId="SYNTHETIC-TEST-TICKET", receiptId="synthetic-test-receipt", runId=operation["runId"],
                      portalId="roads", clientReference=operation["id"], payloadDigest=operation["payloadDigest"],
                      action="create", acceptedAt=utcnow(), receiptUrl="http://test.invalid/receipt", ticketUrl="http://test.invalid/ticket")
    result = cases.record_receipt(operation["id"], ReceiptRecord(worker_id="test-executor", lease_token=job["leaseToken"],
                                 job_id=job["id"], receipt=receipt))
    mail_store = MongoMailStore(db)
    mail_store.ensure_indexes()
    provider = Provider()
    mail = MailService(mail_store, provider, cases, settings)
    mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])
    mail.process_outbox_once()
    mail.poll_once()
    restarted = MailService(MongoMailStore(db), provider, cases, settings)
    restarted.poll_once(full_catchup=True)
    jobs = list(db.jobs.find({"caseId": case["id"], "kind": "follow_up_inspection"}))
    assert len(jobs) == 1
    assert jobs[0]["readOnly"] is True
    assert jobs[0]["operationId"] == operation["id"]
    assert cases.get_case_internal(case["id"])["pendingQuestions"] == []
    assert db.operations.count_documents({"caseId": case["id"], "action": "update"}) == 0
    assert approved["approvedVersion"] == 1
