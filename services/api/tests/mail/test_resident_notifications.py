"""Real case/approval ledger with local-only Atlas and mail provider doubles."""
from dataclasses import replace
from datetime import timedelta
import json

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.main import create_app
from app.mail.config import MailSettings
from app.mail.provider import ProviderFailure
from app.mail.service import MailService
from app.mail.store import MongoMailStore, utcnow
from app.models import (ApprovalRequest, CaseCreate, CasePatch, CaseView, FollowUpAnswer,
                        FollowUpRequest, LeaseRequest, OperationTransition, ReceiptRecord, ResidentNotifications)
from app.service import DomainError

from .test_mail import Provider


def report(email="resident@example.net", **changes):
    value = {"issueId": "roads-pothole", "location": {"municipalityId": "milton-town", "upperTierId": "halton-region",
        "fixtureId": "halton-regional-road", "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "confirmed": True},
        "answers": {"immediateDanger": "No", "roadPosition": "At curb", "travelDirection": "Northbound",
                    "description": "A private synthetic observation that must not enter an email."},
        "notifications": {"email": email, "consent": True} if email else None}
    value.update(changes)
    return CaseCreate.model_validate(value)


@pytest.fixture
def mail(cases, store):
    settings = MailSettings(enabled=True, api_key="test-key", ontara_inbox_id="ontara@agentmail.to",
        authority_inbox_id="authority@agentmail.to", resident_inbox_id="resident@agentmail.to",
        allowed_inbox_ids=frozenset({"ontara@agentmail.to", "authority@agentmail.to", "resident@agentmail.to"}),
        web_base_url="https://ontara.example")
    settings.validate()
    current = MongoMailStore(store.db)
    current.ensure_indexes()
    return MailService(current, Provider(), cases, settings)


def approve(cases, request=None, owner="resident"):
    case = cases.create_case(owner, request or report())
    return cases.approve(case["id"], owner, ApprovalRequest(version=case["version"]))


def acknowledge(cases, case, *, ticket="PRIVATE-TICKET-REFERENCE"):
    leased = cases.lease_job(LeaseRequest(workerId="test-worker", caseId=case["id"]))
    job, operation = leased["job"], leased["operation"]
    cases.transition(operation["id"], OperationTransition(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"],
        expectedState="prepared", state="dispatch_started"))
    return cases.record_receipt(operation["id"], ReceiptRecord(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"], receipt={
        "ticketId": ticket, "receiptId": f"receipt-{operation['caseVersion']}", "runId": operation["runId"], "portalId": operation["portalId"],
        "clientReference": operation["id"], "payloadDigest": operation["payloadDigest"], "action": operation["action"], "acceptedAt": utcnow(),
        "receiptUrl": "https://receiver.example/private-receipt?token=receiver-secret", "ticketUrl": "https://receiver.example/private-ticket?token=receiver-secret",
        "updateUrl": "https://receiver.example/private-update?token=receiver-secret", "formVersion": 1,
    }))


def information_request(cases, result, source="authored-request-1"):
    return cases.request_follow_up(result["case"]["id"], FollowUpRequest(sourceEventId=source, questionIds=["nearestLandmark"],
        reason="The current form requires a nearest landmark.", externalTicketId=result["receipt"]["ticketId"], operationId=result["operation"]["id"]))


@pytest.mark.parametrize("email", ["a@example.net,b@example.net", "a@example.net; b@example.net", "Name <a@example.net>",
    "a@example.net\r\nBcc:attacker@example.net", "a@example.net\n", " a@example.net", "a b@example.net", "a@@example.net",
    "a@localhost", "a@-example.net", "a@example-.net", ".a@example.net", "a..b@example.net", "a.@example.net", "a@127.0.0.1",
    "a@exa_mple.net", "a@例え.net", "a" * 65 + "@example.net"])
def test_only_one_plain_valid_notification_address_is_accepted(email):
    with pytest.raises(ValidationError):
        ResidentNotifications(email=email, consent=True)


@pytest.mark.parametrize("consent", [False, None, "true", 1])
def test_notification_consent_is_explicit(consent):
    with pytest.raises(ValidationError):
        ResidentNotifications(email="resident@example.net", consent=consent)


def test_notification_destination_is_separate_and_frozen_with_approved_version(cases, store):
    case = cases.create_case("resident", report())
    first_version = cases.get_version_internal(case["id"], 1)
    changed = cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=1, notifications={"email": "new@example.net", "consent": True}))
    assert changed["version"] == 2 and changed["notifications"]["email"] == "new@example.net"
    assert cases.get_version_internal(case["id"], 1) == first_version
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=2))
    assert approved["notificationSettingsLocked"] is True
    operation = cases.get_operation_internal(approved["currentOperationId"])
    assert "notifications" not in operation["payload"]
    assert "new@example.net" not in json.dumps(operation["payload"])
    assert cases.get_version_internal(case["id"], 2)["notifications"]["email"] == "new@example.net"
    for preference in ({"email": "other@example.net", "consent": True}, None):
        with pytest.raises(DomainError, match="fixed after the first approval"):
            cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=2, notifications=preference))
    edited = cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=2, answers={**approved["answers"], "description": "An edited private synthetic fact."}))
    assert edited["approvedVersion"] is None and edited["notificationSettingsLocked"] is True
    assert cases.get_version_internal(case["id"], 2)["notifications"]["email"] == "new@example.net"


def test_draft_notification_intent_can_be_cleared_without_mail(cases, mail):
    case = cases.create_case("resident", report())
    cleared = cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=1, notifications=None))
    assert cleared["notifications"] is None and cleared["version"] == 2
    assert mail.tick()["outbox"]["sent"] == 0
    assert mail.store.outbox.count_documents({}) == 0


def test_normal_filing_waits_for_verified_receipt_then_sends_once_without_mock_question(cases, store, mail):
    draft = cases.create_case("resident", report("Resident+case@EXAMPLE.NET"))
    assert mail.tick()["outbox"]["sent"] == 0
    approved = cases.approve(draft["id"], "resident", ApprovalRequest(version=1))
    assert mail.tick()["outbox"]["sent"] == 0
    with pytest.raises(ValueError, match="verified portal operation"):
        mail.on_receipt_verified(draft["id"], cases.get_operation_internal(approved["currentOperationId"]), {"receiptId": "invented"})
    result = acknowledge(cases, approved)
    item = mail.on_receipt_verified(draft["id"], result["operation"], result["receipt"])[0]
    assert item["purpose"] == "RESIDENT_REPORT_FILED"
    assert item["recipients"] == ["Resident+case@example.net"]
    assert mail.store.for_case_purpose(draft["id"], "AUTHORITY_QUESTION") is None
    assert store.db.jobs.count_documents({"caseId": draft["id"], "kind": "follow_up_inspection"}) == 0
    assert mail.process_outbox_once()["sent"] == 1
    restarted = MailService(MongoMailStore(store.db), mail.provider, cases, mail.settings)
    restarted.tick()
    restarted.poll_once(full_catchup=True)
    assert mail.provider.send_count == 1
    observed = cases.get_case(draft["id"], "resident")
    assert observed["stage"] == "report_acknowledged" and observed["pendingQuestions"] == []
    assert observed["notificationProgress"] == [{"id": item["id"], "purpose": "RESIDENT_REPORT_FILED", "state": "SENT",
        "deliveryState": "UNVERIFIED", "updatedAt": mail.store.get(item["id"])["updatedAt"]}]
    CaseView.model_validate(observed)
    notification_events = [event for event in cases.timeline(draft["id"], "resident")["events"] if event["kind"].startswith("notification_")]
    assert [event["kind"] for event in notification_events] == ["notification_queued", "notification_sent"]
    assert "Inbox delivery has not been verified" in notification_events[-1]["message"]
    for private_value in ("Resident+case@example.net", approved["location"]["incidentAddress"], approved["answers"]["description"],
                          result["receipt"]["ticketId"], "receiver-secret", "receiver.example"):
        assert private_value not in item["text"]
        assert private_value not in json.dumps(notification_events, default=str)
    assert f"https://ontara.example/cases/{draft['id']}" in item["text"]
    assert "same browser" in item["text"] and "fictional report" in item["text"]
    assert "reporter" in operation_payload(cases, approved) and operation_payload(cases, approved)["reporter"] is None
    # A fabricated external receiving copy cannot upgrade delivery to RECEIVED.
    external_copy = mail.provider.mail["Resident+case@example.net", mail.store.get(item["id"])["providerMessageId"]]
    assert mail.process_received_message(external_copy) == "ignored"
    assert mail.store.get(item["id"])["deliveryState"] == "UNVERIFIED"


def operation_payload(cases, case):
    return cases.get_operation_internal(case["currentOperationId"])["payload"]


@pytest.mark.parametrize("email", ["resident@agentmail.to", "Resident@agentmail.to"])
def test_controlled_receiver_can_be_observed_without_claiming_human_read(cases, mail, email):
    case = approve(cases, report(email))
    result = acknowledge(cases, case)
    item = mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])[0]
    mail.process_outbox_once()
    if email != "resident@agentmail.to":
        # A provider identifies the existing controlled inbox canonically even
        # when the approved recipient spelling contains an uppercase letter.
        message_id = mail.store.get(item["id"])["providerMessageId"]
        observed = mail.provider.mail.pop((email, message_id))
        observed["inbox_id"] = "resident@agentmail.to"
        mail.provider.mail["resident@agentmail.to", message_id] = observed
    mail.poll_once(full_catchup=True)
    assert mail.store.get(item["id"])["deliveryState"] == "RECEIVED"
    messages = [event["message"] for event in cases.timeline(case["id"], "resident")["events"]]
    assert any("observed in the configured controlled receiving inbox" in text for text in messages)
    assert not any("read by" in text for text in messages)


def test_real_authored_request_is_notified_once_and_update_still_needs_new_approval(cases, store, mail):
    case = approve(cases)
    result = acknowledge(cases, case)
    mail.tick()
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_INFORMATION_NEEDED"}) == 0
    requested = information_request(cases, result)
    information_request(cases, result)
    restarted = MailService(MongoMailStore(store.db), mail.provider, cases, mail.settings)
    restarted.tick()
    restarted.tick()
    item = mail.store.for_case_purpose(case["id"], "RESIDENT_INFORMATION_NEEDED")
    assert item["attemptCount"] == 1 and item["recipients"] == ["resident@example.net"]
    assert "approve the update" in item["text"] and "nearest landmark" not in item["text"]
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_INFORMATION_NEEDED"}) == 1
    saved = cases.answer_follow_up(case["id"], "resident", FollowUpAnswer(expectedVersion=requested["version"], answers={"nearestLandmark": "A private synthetic landmark"}))
    assert saved["approvedVersion"] is None
    mail.tick()
    assert store.db.operations.count_documents({"caseId": case["id"], "action": "update"}) == 0
    approved = cases.approve(case["id"], "resident", ApprovalRequest(version=saved["version"]))
    mail.tick()
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_NOTIFICATION"}) == 0
    updated = acknowledge(cases, approved)
    mail.on_receipt_verified(case["id"], updated["operation"], updated["receipt"])
    mail.tick()
    mail.tick()
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_REPORT_FILED"}) == 1
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_NOTIFICATION"}) == 1
    assert mail.store.outbox.count_documents({"purpose": "AUTHORITY_RESPONSE"}) == 0
    assert mail.provider.send_count == 3
    assert cases.get_case_internal(case["id"])["receipt"]["ticketId"] == result["receipt"]["ticketId"]
    assert all("A private synthetic landmark" not in item["text"] for item in mail.store.outbox.find({}))


def test_report_contact_email_and_historical_records_do_not_opt_into_notifications(cases, store, mail):
    case = approve(cases, report(None, reporter={"email": "contact-only@example.net", "contactConsent": True}))
    result = acknowledge(cases, case)
    store.db.cases.update_one({"id": case["id"]}, {"$unset": {"notificationPolicyVersion": "", "notifications": ""}})
    store.db.case_versions.update_many({"caseId": case["id"]}, {"$unset": {"notificationPolicyVersion": "", "notifications": ""}})
    store.db.operations.update_many({"caseId": case["id"]}, {"$unset": {"notificationPolicyVersion": ""}})
    information_request(cases, result)
    for _ in range(2):
        mail.tick()
    assert mail.provider.send_count == 0 and mail.store.outbox.count_documents({}) == 0
    assert "contact-only@example.net" in json.dumps(operation_payload(cases, case))


def test_missing_fact_during_an_approved_update_uses_existing_ticket_not_unverified_update(cases, store, mail):
    initial = approve(cases)
    receipt = acknowledge(cases, initial)
    changed = cases.patch_case(initial["id"], "resident", CasePatch(expectedVersion=1,
        answers={**initial["answers"], "description": "Another approved synthetic detail."}))
    approved = cases.approve(initial["id"], "resident", ApprovalRequest(version=changed["version"]))
    leased = cases.lease_job(LeaseRequest(workerId="update-worker", caseId=initial["id"]))
    job, operation = leased["job"], leased["operation"]
    assert operation["action"] == "update" and operation["receipt"] is None
    cases.request_follow_up(initial["id"], FollowUpRequest(sourceEventId="current-update-form", questionIds=["nearestLandmark"],
        reason="The current update form requires an additional fact.", externalTicketId=receipt["receipt"]["ticketId"], operationId=operation["id"]))
    cases.transition(operation["id"], OperationTransition(jobId=job["id"], workerId=job["workerId"], leaseToken=job["leaseToken"],
        expectedState="prepared", state="needs_assistance"))
    mail.tick()
    item = mail.store.for_case_purpose(initial["id"], "RESIDENT_INFORMATION_NEEDED")
    assert item["state"] == "SENT" and item["operationId"] == approved["currentOperationId"]
    assert item["receiptId"] == receipt["receipt"]["receiptId"]
    assert store.db.operations.find_one({"id": operation["id"]})["receipt"] is None
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_NOTIFICATION"}) == 0
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_NEEDS_ASSISTANCE"}) == 0


def test_sender_and_recipient_cannot_be_replaced_with_another_cases_address(cases, mail):
    first = approve(cases, report("first@example.net"))
    second = approve(cases, report("second@example.net"), owner="second-owner")
    result = acknowledge(cases, first)
    item = mail.on_receipt_verified(first["id"], result["operation"], result["receipt"])[0]
    mail.store.outbox.update_one({"id": item["id"]}, {"$set": {"recipients": [second["notifications"]["email"]]}})
    assert mail.process_outbox_once()["failed"] == 1
    assert mail.provider.send_count == 0 and mail.store.get(item["id"])["state"] == "CANCELLED"
    with pytest.raises(ValueError):
        mail.settings.require_participants(mail.settings.ontara_inbox_id, ["first@example.net"])
    with pytest.raises(ValueError):
        mail._enqueue(case_id=first["id"], operation=result["operation"], purpose="AUTHORITY_RESPONSE", personal=True,
            sender=mail.settings.ontara_inbox_id, recipients=["first@example.net"], subject="Invalid", text="Invalid", receipt_id=result["receipt"]["receiptId"])


def test_current_unapproved_preferences_cannot_override_approved_snapshot(cases, store, mail):
    case = approve(cases, report("approved@example.net"))
    result = acknowledge(cases, case)
    store.db.cases.update_one({"id": case["id"]}, {"$set": {"notifications.email": "not-approved@example.net"}})
    item = mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])[0]
    assert item["recipients"] == ["approved@example.net"]
    assert mail.process_outbox_once()["sent"] == 1


def test_uncertain_external_send_reconciles_after_restart_without_resending(cases, store, mail):
    case = approve(cases)
    result = acknowledge(cases, case)
    item = mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])[0]
    mail.provider.timeout = "after"
    assert mail.process_outbox_once()["unknown"] == 1
    assert mail.provider.send_count == 1
    mail.store.outbox.update_one({"id": item["id"]}, {"$set": {"nextAttemptAt": utcnow() - timedelta(seconds=1)}})
    restarted = MailService(MongoMailStore(store.db), mail.provider, cases, mail.settings)
    assert restarted.process_outbox_once()["reconciled"] == 1
    restarted.tick()
    assert mail.provider.send_count == 1
    assert mail.store.get(item["id"])["deliveryState"] == "UNVERIFIED"
    kinds = [event["kind"] for event in cases.timeline(case["id"], "resident")["events"]]
    assert kinds.count("notification_outcome_unknown") == 1 and kinds.count("notification_sent") == 1


def test_actual_assistance_event_can_notify_before_receipt_once(cases, store, mail):
    case = approve(cases)
    leased = cases.lease_job(LeaseRequest(workerId="test-worker", caseId=case["id"]))
    job, operation = leased["job"], leased["operation"]
    guard = {"jobId": job["id"], "workerId": job["workerId"], "leaseToken": job["leaseToken"]}
    cases.transition(operation["id"], OperationTransition(**guard, expectedState="prepared", state="needs_assistance"))
    mail.tick()
    mail.tick()
    item = mail.store.for_case_purpose(case["id"], "RESIDENT_NEEDS_ASSISTANCE")
    assert item["attemptCount"] == 1 and item["receiptId"] is None
    assert "has paused" in item["text"] and "filed" not in item["text"]
    assert mail.store.outbox.count_documents({}) == 1
    assert cases.get_case_internal(case["id"])["receipt"] is None
    assert store.db.case_events.count_documents({"kind": "assistance_needed"}) == 1


def test_mail_failure_is_visible_without_recursive_failure_emails(cases, mail, monkeypatch):
    case = approve(cases)
    result = acknowledge(cases, case)
    item = mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])[0]
    def rejected(_):
        raise ProviderFailure("provider_http_400")
    monkeypatch.setattr(mail.provider, "send", rejected)
    assert mail.process_outbox_once()["failed"] == 1
    mail.tick()
    assert mail.store.outbox.count_documents({}) == 1
    assert cases.get_case_internal(case["id"])["notificationProgress"][0]["state"] == "NEEDS_ASSISTANCE"
    assert any(event["kind"] == "notification_needs_assistance" for event in cases.timeline(case["id"], "resident")["events"])


def test_new_advanced_opt_in_preserves_hold_release_and_personal_filing_notification(cases, store, mail):
    draft = cases.create_case("resident", report())
    mail.set_authority_followup_hold(draft["id"], True)
    case = cases.approve(draft["id"], "resident", ApprovalRequest(version=1))
    result = acknowledge(cases, case)
    mail.on_receipt_verified(case["id"], result["operation"], result["receipt"])
    assert mail.process_outbox_once()["sent"] == 1
    question = mail.store.for_case_purpose(case["id"], "AUTHORITY_QUESTION")
    assert question["state"] == "HELD" and question["attemptCount"] == 0
    assert store.db.cases.find_one({"id": case["id"]})["demoControls"]["authorityFollowUpStaged"] is True
    restarted = MailService(MongoMailStore(store.db), mail.provider, cases, mail.settings)
    assert restarted.process_outbox_once()["sent"] == 0
    restarted.set_authority_followup_hold(case["id"], False, portal_confirmation={"runId": case["runId"], "portalId": "roads", "action": "update",
        "formVersion": 2, "snapshotDigest": "a" * 64, "verifiedAt": utcnow().isoformat()})
    restarted.tick()
    assert mail.store.for_case_purpose(case["id"], "AUTHORITY_QUESTION")["deliveryState"] == "RECEIVED"
    assert store.db.jobs.count_documents({"caseId": case["id"], "kind": "follow_up_inspection", "readOnly": True}) == 1
    assert "demoControls" not in cases.get_case_internal(case["id"])


@pytest.mark.parametrize("origin", ["http://untrusted.example", "https://user@ontara.example", "https://ontara.example/cases",
    "https://ontara.example?redirect=evil", "https://ontara.example/#x", "https://ontara.example\n", "//ontara.example"])
def test_email_links_require_a_configured_safe_app_origin(mail, origin):
    with pytest.raises(ValueError, match="app origin"):
        replace(mail.settings, web_base_url=origin).validate()


def test_api_contract_and_case_session_guards_cover_notifications(store, settings, cases, monkeypatch):
    monkeypatch.setenv("ONTARA_MAIL_ENABLED", "false")
    app = create_app(settings, store)
    with TestClient(app) as owner:
        app.state.case_service = cases
        response = owner.post("/v1/cases", json=report().model_dump(by_alias=True))
        assert response.status_code == 201
        case = response.json()
        assert case["notifications"] == {"email": "resident@example.net", "consent": True}
        assert case["notificationSettingsLocked"] is False and case["notificationProgress"] == []
        assert owner.post(f"/v1/cases/{case['id']}/approve", json={"version": 1}).json()["notificationSettingsLocked"] is True
        assert owner.patch(f"/v1/cases/{case['id']}", json={"expectedVersion": 1, "notifications": {"email": "other@example.net", "consent": True}}).status_code == 409
        invalid = report().model_dump(by_alias=True)
        invalid["notifications"] = {"email": "first@example.net,second@example.net", "consent": True}
        assert owner.post("/v1/cases", json=invalid).status_code == 422
        schemas = owner.get("/openapi.json").json()["components"]["schemas"]
        assert "notifications" in schemas["CaseCreate"]["properties"] and "notificationProgress" in schemas["CaseView"]["properties"]
        with TestClient(create_app(settings, store)) as other:
            assert other.get(f"/v1/cases/{case['id']}").status_code == 404
            assert other.get(f"/v1/cases/{case['id']}/timeline").status_code == 404
