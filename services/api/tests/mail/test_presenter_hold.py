"""Private per-case presenter barrier: no timed race and no authorization changes."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.mail.service import MailService
from app.mail.store import MongoMailStore

from .test_mail import env, initial, received


def draft(env):
    service, store, provider, cases, settings = env
    cases.case.update({"runId": "run_demo", "stage": "draft", "approvedVersion": None,
                      "currentOperationId": None, "receipt": None, "cancelledAt": None,
                      "route": {"id": "halton-roads-demo", "demo": True, "portalId": "roads", "recipient": {"id": "halton-region"}},
                      "location": {"fixtureId": "halton-regional-road"}})
    store.db.cases.insert_one(deepcopy(cases.case))
    return env


def verified(env):
    service, store, provider, cases, settings = env
    operation = cases.operations["op_create"]
    operation["runId"] = "run_demo"
    operation["receipt"]["runId"] = "run_demo"
    cases.case.update({"stage": "report_acknowledged", "approvedVersion": 1,
                      "currentOperationId": "op_create", "receipt": deepcopy(operation["receipt"])})
    store.db.cases.update_one({"id": "case_demo"}, {"$set": deepcopy(cases.case)})
    store.db.operations.insert_one(deepcopy(operation))


def proof(**changes):
    return {"runId": "run_demo", "portalId": "roads", "action": "update", "formVersion": 2,
            "snapshotDigest": "a" * 64, "verifiedAt": datetime.now(timezone.utc).isoformat(), **changes}


def test_held_receipt_never_sends_or_schedules_inspection_before_release(env):
    service, store, provider, cases, settings = draft(env)
    before = deepcopy(cases.case)
    assert service.set_authority_followup_hold("case_demo", True)["held"] is True
    verified(env)
    item = initial(service)
    assert item["state"] == "HELD"
    for _ in range(3):
        service.process_outbox_once()
        service.poll_once(full_catchup=True)
    assert provider.send_count == 0
    assert store.get(item["id"])["attemptCount"] == 0
    assert not cases.requests
    # Only presenter metadata changed on the draft; setting the hold never approves it.
    audit = store.db.cases.find_one({"id": "case_demo"})["demoControls"]["authorityFollowUpAudit"]
    assert audit[0]["held"] is True
    assert before["version"] == store.control_case("case_demo")["version"]


def test_release_after_receipt_and_v2_is_idempotent_and_does_not_change_authorization(env):
    service, store, provider, cases, settings = draft(env)
    service.set_authority_followup_hold("case_demo", True)
    verified(env)
    item = initial(service)
    before = store.control_case("case_demo")
    result = service.set_authority_followup_hold("case_demo", False, portal_confirmation=proof())
    assert result["held"] is False
    for _ in range(3):
        assert service.set_authority_followup_hold("case_demo", False, portal_confirmation=proof())["held"] is False
        service.process_outbox_once()
        service.poll_once(full_catchup=True)
    assert provider.send_count == 1
    assert store.outbox.count_documents({"caseId": "case_demo"}) == 1
    assert store.get(item["id"])["attemptCount"] == 1
    assert len(cases.requests) == 1
    after = store.control_case("case_demo")
    for key in ("version", "approvedVersion", "currentOperationId", "receipt", "stage", "location", "route"):
        assert after[key] == before[key]
    assert len(after["demoControls"]["authorityFollowUpAudit"]) == 2


@pytest.mark.parametrize("change", [{"runId": "another_run"}, {"portalId": "graffiti"}, {"action": "create"},
                                    {"formVersion": 1}, {"snapshotDigest": ""}, {"verifiedAt": None}])
def test_release_rejects_wrong_or_missing_portal_confirmation(env, change):
    service, store, provider, cases, _ = draft(env)
    service.set_authority_followup_hold("case_demo", True)
    verified(env)
    item = initial(service)
    with pytest.raises(ValueError, match="v2 follow-up form"):
        service.set_authority_followup_hold("case_demo", False, portal_confirmation=proof(**change))
    service.process_outbox_once()
    assert provider.send_count == 0
    assert store.get(item["id"])["state"] == "HELD"


def test_release_cannot_invent_the_initial_receipt(env):
    service, _, provider, _, _ = draft(env)
    service.set_authority_followup_hold("case_demo", True)
    with pytest.raises(ValueError, match="verified initial receipt"):
        service.set_authority_followup_hold("case_demo", False, portal_confirmation=proof())
    assert provider.send_count == 0


def test_hold_cannot_be_added_after_approval_or_to_a_live_route(env):
    service, store, _, cases, _ = draft(env)
    verified(env)
    with pytest.raises(ValueError, match="before approval"):
        service.set_authority_followup_hold("case_demo", True)
    store.db.cases.update_one({"id": "case_demo"}, {"$set": {"route.demo": False}})
    with pytest.raises(ValueError, match="controlled Roads fixture"):
        service.set_authority_followup_hold("case_demo", True)


def test_restart_preserves_hold_and_repairs_interrupted_release_callback(env):
    service, store, provider, cases, settings = draft(env)
    service.set_authority_followup_hold("case_demo", True)
    verified(env)
    item = initial(service)
    restarted = MailService(MongoMailStore(store.db), provider, cases, settings)
    restarted.process_outbox_once()
    assert provider.send_count == 0
    # Simulate process exit after the authoritative flag/audit commit, before outbox repair.
    case = store.control_case("case_demo")
    assert store.set_control_hold(case, False, proof())
    restarted.process_outbox_once()
    restarted.poll_once()
    assert provider.send_count == 1
    assert store.get(item["id"])["deliveryState"] == "RECEIVED"


def test_repeated_hold_on_same_draft_has_one_audit_entry(env):
    service, store, _, _, _ = draft(env)
    for _ in range(3):
        assert service.set_authority_followup_hold("case_demo", True)["held"] is True
    assert len(store.control_case("case_demo")["demoControls"]["authorityFollowUpAudit"]) == 1


def test_unexpected_inbound_while_held_cannot_bypass_presenter_barrier_or_cause_resend(env):
    service, store, provider, cases, settings = draft(env)
    service.set_authority_followup_hold("case_demo", True)
    verified(env)
    item = initial(service)
    # Simulates a genuine but unexpected provider arrival. Polling may save it, but
    # must not schedule the read-only job until the same-run barrier is released.
    provider.send(item)
    assert service.process_received_message(received(provider, settings)) == "pending"
    assert not cases.requests
    service.set_authority_followup_hold("case_demo", False, portal_confirmation=proof())
    service.process_outbox_once()
    service.poll_once(full_catchup=True)
    assert provider.send_count == 1
    assert len(cases.requests) == 1


def test_hold_is_per_case_and_normal_case_has_no_global_delay(env):
    service, store, provider, cases, _ = draft(env)
    service.set_authority_followup_hold("case_demo", True)
    # A different case's explicit control cannot apply to this normal verified case.
    store.db.cases.update_one({"id": "case_demo"}, {"$set": {"id": "another_held_case"}})
    initial(service)
    service.process_outbox_once()
    assert provider.send_count == 1
