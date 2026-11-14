"""Durable fictional city-email timing; never substitute for a receiver receipt."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.config import Settings
from app.mail.provider import ProviderFailure
from app.mail.service import MailService, SCRIPTED_PURPOSES
from app.mail.store import MongoMailStore
from app.models import ApprovalRequest, CasePatch, CaseView, FollowUpRequest
from app.service import DomainError

from .test_resident_notifications import acknowledge, mail, report


@pytest.fixture
def clock(monkeypatch):
    current = [datetime(2026, 11, 14, 20, 0, tzinfo=timezone.utc)]
    for target in ("app.service.now", "app.mail.service.utcnow", "app.mail.store.utcnow"):
        monkeypatch.setattr(target, lambda: current[0])
    def advance(seconds=0):
        current[0] += timedelta(seconds=seconds)
        return current[0]
    return advance


def draft(cases, *, email="resident@agentmail.to"):
    cases.settings = replace(cases.settings, scripted_email_demo_enabled=True)
    return cases.create_case("resident", report(email))


def approve(cases, case):
    return cases.approve(case["id"], "resident", ApprovalRequest(version=case["version"]))


def prepare(cases, mail):
    case = approve(cases, draft(cases))
    mail.reconcile_scripted_outbox()
    return case, mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_SUBMITTED")


def test_two_scripted_emails_follow_exact_durable_due_times_without_changing_actual_status(cases, store, mail, clock):
    case, first = prepare(cases, mail)
    operation = cases.get_operation_internal(case["currentOperationId"])
    versions = list(store.db.case_versions.find({"caseId": case["id"]}))
    assert first["receiptId"] is None and first["nextAttemptAt"] == clock() + timedelta(seconds=5)
    assert first["subject"].startswith("[Demo] Your report has been submitted [Ontara DEMO ")
    assert "Simulated city update" in first["text"] and "not evidence of actual city acceptance" in first["text"]
    assert mail.process_outbox_once()["sent"] == 0
    clock(4.999)
    assert mail.process_outbox_once()["sent"] == 0
    clock(.001)
    assert mail.process_outbox_once()["sent"] == 1
    first = mail.store.get(first["id"])
    assert first["sentAt"] == operation["scriptedEmailDemo"]["approvedAt"] + timedelta(seconds=5)
    assert first["sentEvidence"] == "provider_send_accepted"
    mail.reconcile_scripted_outbox()
    second = mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_RESOLVED")
    assert second["nextAttemptAt"] == first["sentAt"] + timedelta(seconds=5)
    assert second["subject"].startswith("[Demo] Your issue has been resolved [Ontara DEMO ")
    assert "No real city response or physical repair has been verified" in second["text"]
    clock(4.999)
    assert mail.process_outbox_once()["sent"] == 0
    clock(.001)
    assert mail.process_outbox_once()["sent"] == 1
    mail.poll_once(full_catchup=True)
    observed = cases.get_case_internal(case["id"])
    assert observed["stage"] == case["stage"] == "preparing_report" and observed["receipt"] is None
    assert "demoResolution" not in observed and observed["version"] == case["version"]
    assert cases.get_operation_internal(operation["id"])["state"] == "prepared"
    assert list(store.db.case_versions.find({"caseId": case["id"]})) == versions
    assert set(item["purpose"] for item in mail.store.outbox.find({})) == SCRIPTED_PURPOSES
    assert mail.provider.send_count == 2 and mail.store.messages.count_documents({}) == 4
    assert all(item["attemptCount"] == 1 and item["deliveryState"] == "RECEIVED" for item in mail.store.outbox.find({}))
    CaseView.model_validate(observed)


def test_admission_precedes_email_autosave_but_approval_alone_authorizes_sequence(cases, store, mail, clock):
    case = draft(cases, email=None)
    assert store.db.cases.find_one({"id": case["id"]})["scriptedEmailDemoAdmission"] is True
    assert case["scriptedEmailDemo"] is False
    mail.tick()
    assert mail.store.outbox.count_documents({}) == 0
    cases.settings = replace(cases.settings, scripted_email_demo_enabled=False)
    saved = cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=1, notifications={"email": "resident@agentmail.to", "consent": True}))
    assert saved["scriptedEmailDemo"] is True
    mail.tick()
    assert mail.store.outbox.count_documents({}) == 0
    approved = approve(cases, saved)
    assert cases.get_operation_internal(approved["currentOperationId"])["scriptedEmailDemo"]["enabled"] is True
    mail.reconcile_scripted_outbox()
    assert mail.store.outbox.count_documents({}) == 1


def test_enabling_flag_does_not_enrol_an_older_draft_or_backfill_old_approvals(cases, store, mail, clock):
    old = cases.create_case("resident", report("resident@agentmail.to"))
    cases.settings = replace(cases.settings, scripted_email_demo_enabled=True)
    old = approve(cases, old)
    assert old["scriptedEmailDemo"] is False
    assert "scriptedEmailDemo" not in cases.get_operation_internal(old["currentOperationId"])
    result = acknowledge(cases, old)
    mail.tick()
    clock(20)
    mail.tick()
    assert mail.store.outbox.count_documents({"purpose": {"$in": list(SCRIPTED_PURPOSES)}}) == 0
    assert mail.store.outbox.count_documents({"purpose": "RESIDENT_REPORT_FILED"}) == 1


@pytest.mark.parametrize("advanced", ["hold", "fault"])
def test_advanced_staging_excludes_scripted_mode_before_and_after_approval(cases, store, mail, clock, advanced):
    case = draft(cases)
    if advanced == "hold":
        mail.set_authority_followup_hold(case["id"], True)
    else:
        cases.arm_next_create_fault(case["id"], True)
    assert cases.get_case_internal(case["id"])["scriptedEmailDemo"] is False
    approved = approve(cases, case)
    assert approved["scriptedEmailDemo"] is False
    assert "scriptedEmailDemo" not in cases.get_operation_internal(approved["currentOperationId"])
    mail.reconcile_scripted_outbox()
    assert mail.store.outbox.count_documents({}) == 0


def test_eligibility_rechecks_current_fixture_and_no_email_is_no_opt_in(cases, store, mail, clock):
    case = draft(cases)
    raw = store.db.cases.find_one({"id": case["id"]})
    assert cases._scripted_email_eligible(raw)
    raw["location"]["fixtureId"] = "another-fixture"
    assert not cases._scripted_email_eligible(raw)
    blank = draft(cases, email=None)
    assert approve(cases, blank)["scriptedEmailDemo"] is False
    mail.reconcile_scripted_outbox()
    assert mail.store.outbox.count_documents({}) == 0


@pytest.mark.parametrize("failure", ["unknown", "rejected"])
def test_no_resolved_email_while_first_send_is_unknown_or_failed(cases, mail, clock, monkeypatch, failure):
    case, first = prepare(cases, mail)
    if failure == "unknown":
        mail.provider.timeout = "before"
    else:
        def rejected(_):
            raise ProviderFailure("provider_http_400")
        monkeypatch.setattr(mail.provider, "send", rejected)
    clock(5)
    mail.process_outbox_once()
    for _ in range(3):
        clock(20)
        mail.reconcile_scripted_outbox()
        mail.process_outbox_once()
    assert mail.store.get(first["id"])["attemptCount"] == 1
    assert mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_RESOLVED") is None


def test_unknown_first_can_reconcile_and_stable_sent_time_anchors_second_after_restart(cases, store, mail, clock):
    case, first = prepare(cases, mail)
    mail.provider.timeout = "after"
    clock(5)
    assert mail.process_outbox_once()["unknown"] == 1
    mail.reconcile_scripted_outbox()
    assert mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_RESOLVED") is None
    clock(15)
    restarted = MailService(MongoMailStore(store.db), mail.provider, cases, mail.settings)
    assert restarted.process_outbox_once()["reconciled"] == 1
    original_sent_at = mail.store.get(first["id"])["sentAt"]
    restarted.reconcile_scripted_outbox()
    second = mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_RESOLVED")
    assert second["nextAttemptAt"] == original_sent_at + timedelta(seconds=5)
    clock(1)
    # A later receiving observation or delayed send acknowledgement cannot move
    # a deadline whose original provider acceptance was already recorded.
    mail.store.freeze_sent_time(first["id"], clock(), "receiving_inbox_observation")
    restarted.poll_once(full_catchup=True)
    assert mail.store.get(first["id"])["sentAt"] == original_sent_at
    mail.provider.timeout = None
    clock(4)
    assert restarted.process_outbox_once()["sent"] == 1
    for _ in range(2):
        restarted.tick()
    assert mail.provider.send_count == 2
    assert all(item["attemptCount"] == 1 for item in mail.store.outbox.find({}))


def test_genuine_receiving_proof_can_close_unknown_first_without_missing_timer_anchor(cases, mail, clock):
    case, first = prepare(cases, mail)
    mail.provider.timeout = "after"
    clock(5)
    mail.process_outbox_once()
    mail.poll_once(full_catchup=True)
    first = mail.store.get(first["id"])
    assert first["state"] == "SENT" and first["deliveryState"] == "RECEIVED"
    assert first["sentEvidence"] == "receiving_inbox_observation"
    mail.reconcile_scripted_outbox()
    assert mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_RESOLVED")["nextAttemptAt"] == first["sentAt"] + timedelta(seconds=5)


def test_real_receipt_and_authored_request_do_not_add_extra_emails_to_presentation_case(cases, store, mail, clock):
    case, first = prepare(cases, mail)
    result = acknowledge(cases, case)
    assert mail.on_receipt_verified(case["id"], result["operation"], result["receipt"]) == []
    cases.request_follow_up(case["id"], FollowUpRequest(sourceEventId="authored-local-test", questionIds=["nearestLandmark"],
        reason="A real authored test request", externalTicketId=result["receipt"]["ticketId"], operationId=result["operation"]["id"]))
    mail.reconcile_case_event_outbox()
    clock(5)
    mail.tick()
    clock(5)
    mail.tick()
    assert {item["purpose"] for item in mail.store.outbox.find({})} == SCRIPTED_PURPOSES
    observed = cases.get_case_internal(case["id"])
    assert observed["stage"] == "more_information_needed" and observed["pendingQuestions"]
    assert observed["receipt"]["receiptId"] == result["receipt"]["receiptId"]
    assert store.db.operations.count_documents({"caseId": case["id"]}) == 1


def test_duplicate_approval_and_replay_never_create_another_sequence(cases, store, mail, clock):
    case, first = prepare(cases, mail)
    assert approve(cases, case)["currentOperationId"] == case["currentOperationId"]
    for _ in range(4):
        clock(5)
        mail.tick()
    identities = [(item["id"], item.get("providerMessageId"), item["attemptCount"]) for item in mail.store.outbox.find({})]
    restarted = MailService(MongoMailStore(store.db), mail.provider, cases, mail.settings)
    for _ in range(2):
        restarted.tick()
        approve(cases, case)
    assert identities == [(item["id"], item.get("providerMessageId"), item["attemptCount"]) for item in mail.store.outbox.find({})]
    assert store.db.operations.count_documents({"caseId": case["id"]}) == 1 and mail.provider.send_count == 2


@pytest.mark.parametrize("revoke", ["cancel", "edit"])
def test_cancellation_or_stale_approval_stops_remaining_scripted_send(cases, mail, clock, revoke):
    case, first = prepare(cases, mail)
    clock(5)
    mail.tick()
    if revoke == "cancel":
        cases.cancel(case["id"], "resident")
    else:
        cases.patch_case(case["id"], "resident", CasePatch(expectedVersion=case["version"], answers={**case["answers"], "description": "Changed private fact."}))
    clock(10)
    mail.tick()
    assert mail.provider.send_count == 1
    assert mail.store.for_case_purpose(case["id"], "RESIDENT_SCRIPTED_RESOLVED")["state"] == "CANCELLED"


def test_scripted_recipient_is_the_approved_case_address(cases, mail, clock):
    case, first = prepare(cases, mail)
    mail.store.outbox.update_one({"id": first["id"]}, {"$set": {"recipients": ["another@example.net"]}})
    clock(5)
    assert mail.process_outbox_once()["failed"] == 1 and mail.provider.send_count == 0
    assert mail.store.get(first["id"])["state"] == "CANCELLED"


def test_timer_consumer_is_not_blocked_by_slow_inbound_polling(cases, mail, clock, monkeypatch):
    case = approve(cases, draft(cases))
    clock(5)
    blocked, release, sent = Event(), Event(), Event()
    original_messages, original_send = mail.provider.messages, mail.provider.send
    def slow_messages(*args, **kwargs):
        blocked.set()
        release.wait(3)
        return original_messages(*args, **kwargs)
    def observed_send(item):
        assert blocked.is_set()
        result = original_send(item)
        sent.set()
        return result
    monkeypatch.setattr(mail.provider, "messages", slow_messages)
    monkeypatch.setattr(mail.provider, "send", observed_send)
    try:
        mail.start()
        assert blocked.wait(2) and sent.wait(2)
        assert mail.status(case["id"])["scriptedTimerRunning"]
    finally:
        release.set()
        mail.close()


def test_server_flag_and_new_public_progress_contract_cannot_be_selected_by_request(cases, store, settings, mail, clock, monkeypatch):
    monkeypatch.setenv("ONTARA_MAIL_ENABLED", "false")
    cases.settings = replace(cases.settings, scripted_email_demo_enabled=True)
    app = create_app(cases.settings, store)
    with TestClient(app) as client:
        app.state.case_service = cases
        payload = report("resident@agentmail.to").model_dump(by_alias=True)
        assert client.post("/v1/cases", json=payload | {"scriptedEmailDemo": True}).status_code == 422
        created = client.post("/v1/cases", json=payload).json()
        assert created["scriptedEmailDemo"] is True
        assert "scriptedEmailDemoAdmission" not in created and "scriptedEmailDemoOperationId" not in created
        assert client.patch(f"/v1/cases/{created['id']}", json={"expectedVersion": 1, "scriptedEmailDemoAdmission": True}).status_code == 422
        schema = client.get("/openapi.json").json()["components"]["schemas"]
        assert "scriptedEmailDemo" in schema["CaseView"]["properties"]
        assert SCRIPTED_PURPOSES <= set(schema["NotificationProgress"]["properties"]["purpose"]["enum"])


def test_scripted_flag_defaults_off_and_is_loaded_only_from_server_configuration(tmp_path, monkeypatch):
    file = tmp_path / "empty.env"
    file.write_text("")
    monkeypatch.delenv("ONTARA_SCRIPTED_EMAIL_DEMO_ENABLED", raising=False)
    assert Settings.load(str(file)).scripted_email_demo_enabled is False
    monkeypatch.setenv("ONTARA_SCRIPTED_EMAIL_DEMO_ENABLED", "true")
    assert Settings.load(str(file)).scripted_email_demo_enabled is True


spec = importlib.util.spec_from_file_location("observe_scripted_demo", Path(__file__).resolve().parents[4] / "scripts/mail/observe_scripted_demo.py")
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def test_observer_resumes_same_case_with_gets_and_only_exports_safe_timing(cases, store, mail, clock):
    case, first = prepare(cases, mail)
    clock(5)
    mail.tick()
    clock(5)
    mail.tick()
    def json_ready(value):
        return json.loads(json.dumps(value, default=lambda item: item.isoformat()))
    calls = []
    def get(path):
        calls.append(path)
        if "/operations/" in path:
            return json_ready(cases.get_operation_internal(case["currentOperationId"]))
        if "/mail/status" in path:
            result = json_ready(mail.status(case["id"]))
            # Providers may use different thread IDs in separate inboxes.
            for item in result["outbox"]:
                item["receivingEvidence"]["providerThreadId"] = "actual-receiver-thread"
            return result
        return json_ready(cases.get_case_internal(case["id"]))
    one = observer.collect(case["id"], get)
    two = observer.collect(case["id"], get)
    assert one["qualified"] and two["qualified"] and len(calls) == 6
    assert one["timing"] == {"firstSentAfterApprovalSeconds": 5.0, "secondSentAfterFirstSentSeconds": 5.0, "bothMinimumFiveSeconds": True}
    assert all(row["receivingObservedAt"] and row["approvedRecipientMatches"] for row in one["notifications"])
    for private in ("resident@agentmail.to", "ontara@agentmail.to", case["currentOperationId"], case["runId"], case["location"]["incidentAddress"]):
        assert private not in json.dumps(one)
    assert mail.provider.send_count == 2 and store.db.operations.count_documents({"caseId": case["id"]}) == 1


def test_observer_requires_owner_only_config_and_safe_api_origin(tmp_path):
    private = tmp_path / "cloud.env"
    private.write_text("ONTARA_INTERNAL_TOKEN=test-only\n")
    private.chmod(0o600)
    assert observer.private_config(str(private))["ONTARA_INTERNAL_TOKEN"] == "test-only"
    private.chmod(0o644)
    with pytest.raises(ValueError):
        observer.private_config(str(private))
    for value in ("https://evil.example", "http://api.onrender.com", "https://token@api.onrender.com", "https://api.onrender.com/path"):
        with pytest.raises(ValueError):
            observer.api_origin(value)
