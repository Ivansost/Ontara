from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import (ApprovalRequest, CaseCreate, CasePatch, FollowUpAnswer, FollowUpInspectionRequest,
                        FollowUpRequest, LeaseRequest, OperationTransition, ReceiptRecord)
from app.service import DomainError
from app.storage import now


def report(**overrides):
    data = {"issueId": "roads-pothole", "location": {"municipalityId": "milton-town", "upperTierId": "halton-region",
        "fixtureId": "halton-regional-road", "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True},
        "answers": {"immediateDanger": "No", "roadPosition": "At curb", "travelDirection": "Northbound", "description": "A synthetic pothole next to the curb."}}
    data.update(overrides)
    return CaseCreate.model_validate(data)


def approve(cases, owner="resident"):
    case = cases.create_case(owner, report())
    return cases.approve(case["id"], owner, ApprovalRequest(version=case["version"]))


def transition(cases, leased, state, expected):
    job = leased["job"]
    return cases.transition(leased["operation"]["id"], OperationTransition(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"], expectedState=expected, state=state))


def acknowledge(cases, case):
    leased = cases.lease_job(LeaseRequest(workerId="worker-1", caseId=case["id"]))
    op = transition(cases, leased, "dispatch_started", "prepared")
    receipt = {"ticketId": "ticket-test", "receiptId": "receipt-test", "runId": op["runId"], "portalId": op["portalId"],
               "clientReference": op["id"], "payloadDigest": op["payloadDigest"], "action": op["action"], "acceptedAt": now(),
               "receiptUrl": "https://portals.example/receipt", "ticketUrl": "https://portals.example/ticket", "updateUrl": "https://portals.example/update?token=private", "formVersion": 1}
    job = leased["job"]
    result = cases.record_receipt(op["id"], ReceiptRecord(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"], receipt=receipt))
    return result, leased


def test_inactive_and_unverified_routes_cannot_create_private_data(cases, store):
    with pytest.raises(DomainError):
        cases.create_case("resident", report(issueId="waste-missed-collection"))
    request = report()
    request.location.fixture_id = "unknown-road"
    with pytest.raises(DomainError):
        cases.create_case("resident", request)
    assert store.db.cases.count_documents({}) == 0
    assert store.db.case_versions.count_documents({}) == 0


def test_residence_does_not_override_incident_ownership(cases):
    request = report()
    request.location.reporter_municipality_id = "toronto-city"
    case = cases.create_case("resident", request)
    assert case["route"]["authorityId"] == "halton-region"
    request.location.municipality_id = "toronto-city"
    request.location.reporter_municipality_id = "milton-town"
    with pytest.raises(DomainError):
        cases.create_case("resident", request)


def test_private_case_requires_own_session(cases):
    case = cases.create_case("alice", report())
    with pytest.raises(DomainError) as error:
        cases.get_case(case["id"], "bob")
    assert error.value.status == 404
    assert "ownerKey" not in cases.get_case(case["id"], "alice")


def test_material_edit_invalidates_approval_and_preserves_version(cases, store):
    case = approve(cases)
    original = cases.get_version_internal(case["id"], 1)
    updated = cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=1, answers={**case["answers"], "description": "Changed synthetic observation at same curb."}))
    assert updated["version"] == 2 and updated["approvedVersion"] is None
    assert cases.get_version_internal(case["id"], 1) == original
    assert store.db.jobs.find_one({"caseId": case["id"]})["state"] == "cancelled"
    with pytest.raises(DomainError) as error:
        cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    assert error.value.status == 409


def test_duplicate_approval_even_after_receipt_never_creates_update(cases, store):
    case = approve(cases)
    cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    acknowledge(cases, case)
    cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    assert store.db.operations.count_documents({"caseId": case["id"]}) == 1
    assert store.db.jobs.count_documents({"caseId": case["id"]}) == 1


def test_expired_worker_cannot_transition_after_new_lease(cases, store):
    case = approve(cases)
    old = cases.lease_job(LeaseRequest(workerId="worker-old", caseId=case["id"]))
    store.db.jobs.update_one({"id": old["job"]["id"]}, {"$set": {"leaseUntil": now() - timedelta(seconds=1)}})
    fresh = cases.lease_job(LeaseRequest(workerId="worker-fresh", caseId=case["id"]))
    assert fresh["job"]["fence"] > old["job"]["fence"]
    with pytest.raises(DomainError):
        transition(cases, old, "dispatch_started", "prepared")
    transition(cases, fresh, "dispatch_started", "prepared")


def test_crash_reclaims_same_operation_for_reconciliation(cases, store):
    case = approve(cases)
    cases.arm_fault(case["currentOperationId"], True)
    first = cases.lease_job(LeaseRequest(workerId="process-1", caseId=case["id"]))
    assert first["job"]["faultAfterAcceptance"] is True
    transition(cases, first, "dispatch_started", "prepared")
    cases.abandon(first["job"]["id"], "process-1", first["job"]["leaseToken"], {"exitCode": -9})
    second = cases.lease_job(LeaseRequest(workerId="process-2", caseId=case["id"]))
    assert second["operation"]["id"] == first["operation"]["id"]
    assert second["operation"]["state"] == "dispatch_started"
    assert second["job"]["faultAfterAcceptance"] is False
    transition(cases, second, "reconciling", "dispatch_started")
    assert store.db.operations.count_documents({}) == 1


def test_mail_schedules_only_readonly_inspection_then_explicit_update_approval(cases, store):
    case = approve(cases)
    acknowledged, _ = acknowledge(cases, case)
    request = FollowUpInspectionRequest(sourceEventId="provider-message-1", reason="Please clarify location", externalTicketId="ticket-test", operationId=case["currentOperationId"])
    inspection = cases.request_follow_up_inspection(case["id"], request)
    assert cases.request_follow_up_inspection(case["id"], request)["id"] == inspection["id"]
    assert cases.get_case_internal(case["id"])["pendingQuestions"] == []
    leased = cases.lease_job(LeaseRequest(workerId="inspector", jobId=inspection["id"]))
    assert leased["job"]["readOnly"] and leased["operation"]["state"] == "receipt_verified"
    with pytest.raises(DomainError):
        transition(cases, leased, "dispatch_started", "receipt_verified")
    cases.request_follow_up(case["id"], FollowUpRequest(sourceEventId="provider-message-1", questionIds=["nearestLandmark"], reason="Current form requires a landmark", externalTicketId="ticket-test"))
    cases.inspection_result(inspection["id"], "inspector", leased["job"]["leaseToken"], "needs_input", "Missing landmark", {})
    saved = cases.answer_follow_up(case["id"], "resident", FollowUpAnswer(expectedVersion=1, answers={"nearestLandmark": "Synthetic bus shelter"}))
    assert saved["approvedVersion"] is None
    assert store.db.operations.count_documents({}) == 1
    updated = cases.approve(case["id"], "resident", ApprovalRequest(version=saved["version"]))
    operation = cases.get_operation_internal(updated["currentOperationId"])
    assert operation["action"] == "update" and operation["externalTicketId"] == "ticket-test"
    assert operation["payload"]["answers"]["nearestLandmark"] == "Synthetic bus shelter"


def test_receipt_must_match_exact_approved_payload(cases):
    case = approve(cases)
    leased = cases.lease_job(LeaseRequest(workerId="worker", caseId=case["id"]))
    op = transition(cases, leased, "dispatch_started", "prepared")
    receipt = {"ticketId": "ticket", "receiptId": "receipt", "runId": op["runId"], "portalId": "roads", "clientReference": op["id"], "payloadDigest": "wrong", "action": "create", "acceptedAt": now(), "receiptUrl": "https://example/receipt", "ticketUrl": "https://example/ticket"}
    with pytest.raises(DomainError):
        cases.record_receipt(op["id"], ReceiptRecord(jobId=leased["job"]["id"], workerId="worker", leaseToken=leased["job"]["leaseToken"], receipt=receipt))
    assert cases.get_case_internal(case["id"])["receipt"] is None


def test_cancel_revokes_queued_and_leased_actions(cases):
    case = approve(cases)
    leased = cases.lease_job(LeaseRequest(workerId="worker", caseId=case["id"]))
    cases.cancel(case["id"], "resident")
    with pytest.raises(DomainError):
        transition(cases, leased, "dispatch_started", "prepared")


def test_native_procedure_unavailable_or_changed_cannot_authorize(cases, monkeypatch, store):
    case = cases.create_case("resident", report())
    monkeypatch.setattr(cases, "_knowledge", lambda *_: {"status": "pending", "evidence": {"nativeQuery": False}})
    with pytest.raises(DomainError):
        cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    assert store.db.operations.count_documents({}) == 0


def test_graffiti_asset_scope_is_checked_before_draft(cases, store):
    location = {"municipalityId": "milton-town", "upperTierId": "halton-region", "fixtureId": "milton-public-wall", "incidentAddress": "Synthetic municipal public wall, Milton", "confirmed": True}
    case = cases.create_case("resident", report(issueId="graffiti-wall", location=location, answers={"immediateDanger": "No", "surfaceType": "Public wall", "offensiveContent": "Not sure", "description": "Synthetic graffiti on the public wall."}))
    assert case["route"]["authorityId"] == "milton-town"
    with pytest.raises(DomainError):
        cases.create_case("resident", report(issueId="graffiti-building", location=location, answers={}))


def test_retaining_fixture_id_cannot_authorize_changed_incident_address(cases, store):
    request = report()
    request.location.incident_address = "Different road in a different place"
    with pytest.raises(DomainError):
        cases.create_case("resident", request)
    assert store.db.cases.count_documents({}) == 0
