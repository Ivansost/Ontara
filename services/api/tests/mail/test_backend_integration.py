"""Exercise the actual case-service contract; mail transport is a test double here."""
import mongomock

from app.config import Settings
from app.mail.service import MailService
from app.mail.store import MongoMailStore, utcnow
from app.models import ApprovalRequest, CaseCreate, LeaseRequest, OperationTransition, Receipt, ReceiptRecord
from app.service import CaseService
from app.storage import Store

from .test_mail import Provider, env


def test_explicitly_staged_backend_schedules_one_read_only_inspection_without_question(env, monkeypatch):
    settings = env[-1]
    db = mongomock.MongoClient(tz_aware=True).ontara
    store = Store(db, transactions=False)
    store.ensure_indexes()
    cases = CaseService(store, Settings())
    # This test verifies mail/ledger ordering, not Atlas native retrieval. Mongomock
    # has no search-index/text-query implementation; the production native gate stays intact.
    monkeypatch.setattr(cases, "_knowledge", lambda issue_id, authority_id: {
        "status": "ready", "evidence": {"testFixture": True, "nativeQuery": False},
        "selected": {"id": "test-fixture-halton-roads", "authorityId": authority_id,
                     "sourceVersion": "test-fixture-1", "verificationStatus": "verified",
                     "integrationStatus": "demo_tested", "title": "Test fixture only",
                     "sourceRefs": [{"id": "test-fixture-source", "sourceVersion": "test-fixture-1",
                                     "title": "Test fixture only", "url": "https://example.invalid/test-fixture"}]},
    })
    case = cases.create_case("synthetic-test-session", CaseCreate(
        issueId="roads-pothole",
        location={"municipalityId": "milton-town", "upperTierId": "halton-region",
                  "fixtureId": "halton-regional-road", "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True},
        answers={"immediateDanger": "No", "roadPosition": "In travel lane", "travelDirection": "Northbound",
                 "description": "A synthetic pothole for a test."},
    ))
    mail_store = MongoMailStore(db)
    mail_store.ensure_indexes()
    provider = Provider()
    mail = MailService(mail_store, provider, cases, settings)
    mail.set_authority_followup_hold(case["id"], True)
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
    mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])
    assert mail.process_outbox_once()["sent"] == 0
    mail.set_authority_followup_hold(case["id"], False, portal_confirmation={
        "runId": case["runId"], "portalId": "roads", "action": "update", "formVersion": 2,
        "snapshotDigest": "a" * 64, "verifiedAt": utcnow().isoformat(),
    })
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
