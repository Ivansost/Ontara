import pytest

from app.models import (ApprovalRequest, CaseCreate, FollowUpInspectionRequest, LeaseRequest,
                        OperationTransition, ReceiptRecord)
from app.storage import now


@pytest.fixture
def acknowledged_case(cases):
    case = cases.create_case("resident", CaseCreate(issueId="roads-pothole", location={
        "municipalityId": "milton-town", "upperTierId": "halton-region", "fixtureId": "halton-regional-road",
        "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True}, answers={
        "immediateDanger": "No", "roadPosition": "At curb", "travelDirection": "Northbound", "description": "Synthetic pothole for event truthfulness tests."}))
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    leased = cases.lease_job(LeaseRequest(workerId="test-worker", caseId=case["id"]))
    job, operation = leased["job"], leased["operation"]
    cases.transition(operation["id"], OperationTransition(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"],
                                                        expectedState="prepared", state="dispatch_started"))
    cases.record_receipt(operation["id"], ReceiptRecord(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"], receipt={
        "ticketId": "unit-ticket", "receiptId": "unit-receipt", "runId": case["runId"], "portalId": "roads",
        "clientReference": operation["id"], "payloadDigest": operation["payloadDigest"], "action": "create", "acceptedAt": now(),
        "receiptUrl": "https://portal.example/receipt", "ticketUrl": "https://portal.example/ticket"}))
    return case, operation


def test_withheld_inspection_is_a_presenter_diagnostic_without_invented_mail(cases, store, acknowledged_case):
    case, operation = acknowledged_case
    request = FollowUpInspectionRequest(sourceEventId="presenter:withheld-comparison", reason="Controlled comparison before releasing mail",
        externalTicketId="unit-ticket", operationId=operation["id"], withholdLessonIds=["verified-lesson"])
    job = cases.request_follow_up_inspection(case["id"], request)
    assert cases.request_follow_up_inspection(case["id"], request)["id"] == job["id"]
    event = store.db.case_events.find_one({"caseId": case["id"], "kind": "diagnostic_inspection_requested"})
    assert event["visibility"] == "presenter"
    assert "no new authority email" in event["message"] and "authorizes no portal write" in event["message"]
    assert event["data"]["diagnostic"] is True
    assert event["data"]["sourceEventId"] == request.source_event_id
    assert store.db.case_events.count_documents({"caseId": case["id"], "kind": "diagnostic_inspection_requested"}) == 1
    assert store.db.case_events.count_documents({"caseId": case["id"], "kind": "follow_up_received"}) == 0
    assert all(item["kind"] != "diagnostic_inspection_requested" for item in cases.timeline(case["id"], "resident")["events"])
    assert job["readOnly"] is True and cases.get_operation_internal(operation["id"])["state"] == "receipt_verified"
    assert store.db.operations.count_documents({"caseId": case["id"], "action": "update"}) == 0


def test_genuine_provider_inspection_keeps_resident_event_and_source_identity(cases, store, acknowledged_case):
    case, operation = acknowledged_case
    request = FollowUpInspectionRequest(sourceEventId="agentmail:provider-message", reason="Actual correlated authority message",
        externalTicketId="unit-ticket", operationId=operation["id"])
    job = cases.request_follow_up_inspection(case["id"], request)
    event = store.db.case_events.find_one({"caseId": case["id"], "kind": "follow_up_received"})
    assert event["visibility"] == "resident"
    assert event["message"] == "The simulated authority requested more information. Ontara is checking the current receiving form."
    assert event["data"] == {"sourceEventId": request.source_event_id, "inspectionJobId": job["id"]}
    assert any(item["id"] == event["id"] for item in cases.timeline(case["id"], "resident")["events"])
    assert store.db.case_events.count_documents({"caseId": case["id"], "kind": "diagnostic_inspection_requested"}) == 0
