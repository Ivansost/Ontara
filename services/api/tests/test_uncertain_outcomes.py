import pytest

from app.models import (ApprovalRequest, CaseCreate, CasePatch, FollowUpAnswer, FollowUpRequest,
                        LeaseRequest, OperationTransition, ReceiptRecord)
from app.service import DomainError
from app.storage import now


def report():
    return CaseCreate(issueId="graffiti-wall", location={"municipalityId": "milton-town", "upperTierId": "halton-region",
        "fixtureId": "milton-public-wall", "incidentAddress": "Synthetic municipal public wall, Milton", "confirmed": True},
        answers={"immediateDanger": "No", "surfaceType": "Public wall", "offensiveContent": "Not sure", "description": "Synthetic public wall graffiti."})


def approved_and_leased(cases):
    case = cases.create_case("resident", report())
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    leased = cases.lease_job(LeaseRequest(workerId="worker", caseId=case["id"]))
    return approved, leased


def change(cases, leased, before, after, evidence=None):
    job = leased["job"]
    return cases.transition(leased["operation"]["id"], OperationTransition(jobId=job["id"], workerId=job["workerId"],
        leaseToken=job["leaseToken"], expectedState=before, state=after, evidence=evidence or {}))


@pytest.mark.parametrize("legacy", [False, True])
def test_uncertain_assistance_blocks_edit_and_approval_and_cancel_keeps_truth(cases, store, legacy):
    case, leased = approved_and_leased(cases)
    change(cases, leased, "prepared", "dispatch_started")
    uncertain = change(cases, leased, "dispatch_started", "needs_assistance")
    assert uncertain["dispatchStartedAt"] and uncertain["outcomeUncertain"] is True
    if legacy:
        store.db.operations.update_one({"id": uncertain["id"]}, {"$unset": {"dispatchStartedAt": "", "outcomeUncertain": ""}})
    with pytest.raises(DomainError) as edit:
        cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=1, answers={**case["answers"], "description": "Changed while old submission is uncertain."}))
    assert edit.value.status == 409
    with pytest.raises(DomainError) as approval:
        cases.approve(case["id"], "resident", ApprovalRequest(version=1))
    assert approval.value.status == 409
    assert store.db.operations.count_documents({"caseId": case["id"], "action": "create"}) == 1
    assert store.db.case_versions.count_documents({"caseId": case["id"]}) == 1
    cancelled = cases.cancel(case["id"], "resident")
    assert cancelled["stage"] == "cancelled"
    assert cases.get_operation_internal(uncertain["id"])["state"] == "needs_assistance"
    cancellation = cases.timeline(case["id"], "resident")["events"][-1]
    assert cancellation["data"]["outcomeUncertain"] is True
    assert cancellation["data"]["unresolvedOperationId"] == uncertain["id"]
    with pytest.raises(DomainError):
        cases.approve(case["id"], "resident", ApprovalRequest(version=1))


def test_pre_dispatch_follow_up_pause_can_save_answer_and_approve_same_ticket(cases, store):
    case, initial = approved_and_leased(cases)
    op = change(cases, initial, "prepared", "dispatch_started")
    job = initial["job"]
    cases.record_receipt(op["id"], ReceiptRecord(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"], receipt={
        "ticketId": "existing-ticket", "receiptId": "initial-receipt", "runId": op["runId"], "portalId": op["portalId"],
        "clientReference": op["id"], "payloadDigest": op["payloadDigest"], "action": "create", "acceptedAt": now(),
        "receiptUrl": "https://portals.example/receipt", "ticketUrl": "https://portals.example/ticket"}))
    cases.request_follow_up(case["id"], FollowUpRequest(sourceEventId="first-fact", questionIds=["nearestLandmark"], reason="Known missing fact", externalTicketId="existing-ticket"))
    saved = cases.answer_follow_up(case["id"], "resident", FollowUpAnswer(expectedVersion=1, answers={"nearestLandmark": "Known synthetic landmark"}))
    cases.approve(case["id"], "resident", ApprovalRequest(version=saved["version"]))
    update = cases.lease_job(LeaseRequest(workerId="worker", caseId=case["id"]))
    paused = change(cases, update, "prepared", "needs_assistance")
    assert not paused.get("dispatchStartedAt") and not paused.get("outcomeUncertain")
    cases.request_follow_up(case["id"], FollowUpRequest(sourceEventId="clarify-fact", questionIds=["nearestLandmark"], reason="Clarify before any write", externalTicketId="existing-ticket"))
    clarified = cases.answer_follow_up(case["id"], "resident", FollowUpAnswer(expectedVersion=saved["version"], answers={"nearestLandmark": "Corrected synthetic landmark"}))
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=clarified["version"]))
    latest = cases.get_operation_internal(approved["currentOperationId"])
    assert latest["action"] == "update" and latest["externalTicketId"] == "existing-ticket"
    assert store.db.operations.count_documents({"caseId": case["id"], "action": "create"}) == 1


def test_authoritative_non_application_clears_uncertainty_without_losing_dispatch_history(cases):
    case, leased = approved_and_leased(cases)
    change(cases, leased, "prepared", "dispatch_started")
    change(cases, leased, "dispatch_started", "outcome_unknown")
    change(cases, leased, "outcome_unknown", "reconciling")
    prepared = change(cases, leased, "reconciling", "prepared", {"safeNonApplicationEvidence": {"receiverLookup": "authoritative_not_applied"}})
    assert prepared["dispatchStartedAt"] and prepared["outcomeUncertain"] is False
    change(cases, leased, "prepared", "needs_assistance")
    edited = cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=1, answers={**case["answers"], "description": "Changed after authoritative non-application was established."}))
    assert edited["version"] == 2
