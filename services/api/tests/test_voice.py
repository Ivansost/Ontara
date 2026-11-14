from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError

from app.catalogue import DEMO_LOCATIONS
from app.models import CaseCreate, CasePatch
from app.service import DomainError
from app.storage import now
from app.voice.models import VoiceAnswer, VoiceBind, VoiceStart
from app.voice.provider import ElevenLabsGateway, VoiceSettings
from app.voice.service import VoiceService


class FakeGateway:
    def __init__(self):
        self.started = 0
        self.actual = None

    def signed_session(self):
        self.started += 1
        conversation = f"conv_controlled_fixture_{self.started}"
        return {"conversationId": conversation,
                "signedUrl": f"wss://api.elevenlabs.io/v1/convai/conversation?conversation_id={conversation}&conversation_signature=private-capability"}

    def conversation(self, conversation_id):
        if self.actual is None:
            raise DomainError(503, "Provider transcript not ready")
        return self.actual


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
def voice(store, cases, gateway):
    return VoiceService(store.db, cases, VoiceSettings(enabled=True, api_key="test-private-key", agent_id="agent_controlled"), gateway)


def start_request(**changes):
    fixture = next(x for x in DEMO_LOCATIONS if x["fixtureId"] == "halton-regional-road")
    request = {"requestId": "controlled_request_001", "issueId": "roads-pothole", "location": {
        "municipalityId": fixture["municipalityId"], "upperTierId": fixture["upperTierId"],
        "incidentAddress": fixture["incidentAddress"], "fixtureId": fixture["fixtureId"], "confirmed": True},
        "answers": {}, "voiceConsent": True, "consentVersion": "2026-11-14.1"}
    return VoiceStart.model_validate({**request, **changes})


def answer(voice, state, question_id, value, owner="owner-1"):
    return voice.answer(state["id"], owner, VoiceAnswer(expected_revision=state["revision"], question_id=question_id, value=value))


def draft_case(cases, answers=None):
    request = start_request()
    return cases.create_case("owner-1", CaseCreate(issue_id=request.issue_id, location=request.location, answers=answers or {}))


def test_canonical_question_session_saves_no_capability_or_case(voice, store, gateway):
    issued = voice.start("owner-1", start_request())
    state = issued["session"]
    assert state["nextQuestion"]["id"] == "immediateDanger"
    assert state["questionnaireVersion"] == "2026-11-14.2"
    assert "Regional Roads Portal" in state["recipientName"]
    assert gateway.started == 1
    saved = store.db.voice_sessions.find_one({"id": state["id"]})
    assert saved["consent"]["audioRecording"] is False
    assert "signedUrl" not in saved and "private-capability" not in str(saved)
    assert store.db.cases.count_documents({}) == 0
    assert store.db.jobs.count_documents({}) == 0
    assert store.db.call_records.count_documents({}) == 0


def test_explicit_consent_and_no_approval_contract():
    with pytest.raises(ValidationError):
        start_request(voiceConsent=False)
    with pytest.raises(ValidationError):
        start_request(approved=True)
    with pytest.raises(ValidationError):
        start_request(consentVersion="unknown")


def test_inactive_and_unsupported_routes_save_nothing(voice, store, gateway):
    with pytest.raises(DomainError) as error:
        voice.start("owner-1", start_request(issueId="waste-missed-collection"))
    assert error.value.status == 422
    bad = start_request()
    bad.location.municipality_id = "toronto"
    with pytest.raises(DomainError):
        voice.start("owner-1", bad)
    assert store.db.voice_sessions.count_documents({}) == 0
    assert gateway.started == 0


def test_disabled_feature_does_not_start_or_save(voice, store, gateway, cases):
    disabled = VoiceService(store.db, cases, VoiceSettings(), gateway)
    with pytest.raises(DomainError) as error:
        disabled.start("owner-1", start_request())
    assert error.value.status == 503
    assert store.db.voice_sessions.count_documents({}) == 0
    assert gateway.started == 0


def test_other_issue_and_follow_up_ids_cannot_enter_intake(voice):
    for answers in ({"approvedVersion": "1"}, {"nearestLandmark": "A bench"}, {"surfaceType": "Public wall"}):
        with pytest.raises(DomainError):
            voice.start("owner-1", start_request(answers=answers))


def test_only_current_visible_question_accepts_exact_allowed_value(voice):
    state = voice.start("owner-1", start_request())["session"]
    with pytest.raises(DomainError):
        answer(voice, state, "description", "Do this before the hazard question")
    with pytest.raises(DomainError):
        answer(voice, state, "immediateDanger", "not an allowed choice")
    with pytest.raises(DomainError):
        answer(voice, state, "immediateDanger", None)
    updated = answer(voice, state, "immediateDanger", "No")
    assert updated["nextQuestion"]["id"] == "roadPosition"
    with pytest.raises(DomainError) as error:
        answer(voice, state, "immediateDanger", "No")
    assert error.value.status == 409


def test_urgent_answer_stops_questions_and_never_dispatches(voice, store):
    state = voice.start("owner-1", start_request())["session"]
    updated = answer(voice, state, "immediateDanger", "Yes")
    assert updated["status"] == "urgent_handoff" and updated["nextQuestion"] is None
    assert "urgent" in updated["message"]
    with pytest.raises(DomainError):
        answer(voice, updated, "roadName", "Demo road")
    assert store.db.cases.count_documents({}) == 0
    assert store.db.jobs.count_documents({}) == 0
    assert store.db.operations.count_documents({}) == 0


def test_authored_intake_branch_optional_skip_and_review(voice):
    state = voice.start("owner-1", start_request())["session"]
    values = {"immediateDanger": "No", "roadPosition": "Not sure", "travelDirection": "Not sure", "observedAt": None,
              "description": "A synthetic pothole is visible beside the demo marker."}
    seen = []
    while state["nextQuestion"]:
        question_id = state["nextQuestion"]["id"]
        seen.append(question_id)
        state = answer(voice, state, question_id, values[question_id])
    assert "observedAt" in seen
    assert state["status"] == "ready_for_review"
    assert "Nothing has been sent by voice" in state["reviewText"]
    assert "Regional Roads Portal" in state["reviewText"]
    assert "observedAt" not in state["answers"]


def test_cross_session_access_and_expiry(voice, store):
    state = voice.start("owner-1", start_request())["session"]
    for action in (lambda: voice.read(state["id"], "owner-2"),
                   lambda: answer(voice, state, "immediateDanger", "No", "owner-2"),
                   lambda: voice.finish(state["id"], "owner-2")):
        with pytest.raises(DomainError) as error:
            action()
        assert error.value.status == 404
    store.db.voice_sessions.update_one({"id": state["id"]}, {"$set": {"expiresAt": now() - timedelta(seconds=1)}})
    with pytest.raises(DomainError) as error:
        voice.read(state["id"], "owner-1")
    assert error.value.status == 409


def test_start_replay_and_owner_quota(voice, gateway):
    voice.start("owner-1", start_request())
    with pytest.raises(DomainError) as error:
        voice.start("owner-1", start_request())
    assert error.value.status == 409 and gateway.started == 1
    voice.start("owner-1", start_request(requestId="controlled_request_002"))
    voice.start("owner-1", start_request(requestId="controlled_request_003"))
    with pytest.raises(DomainError) as error:
        voice.start("owner-1", start_request(requestId="controlled_request_004"))
    assert error.value.status == 429 and gateway.started == 3


def test_reserved_session_is_not_a_fabricated_call(voice, store, cases):
    state = voice.start("owner-1", start_request())["session"]
    case = draft_case(cases)
    voice.bind(state["id"], "owner-1", VoiceBind(case_id=case["id"], case_version=case["version"]))
    result = voice.finish(state["id"], "owner-1")
    assert result["transcriptStatus"] == "pending"
    assert store.db.call_records.count_documents({}) == 0
    with pytest.raises(DomainError):
        answer(voice, state, "immediateDanger", "No")


def test_restart_catches_up_actual_transcript_after_browser_close(voice, gateway, store, cases):
    issued = voice.start("owner-1", start_request())
    case = draft_case(cases)
    voice.bind(issued["session"]["id"], "owner-1", VoiceBind(case_id=case["id"], case_version=1))
    store.db.voice_sessions.update_one({"id": issued["session"]["id"]},
        {"$set": {"createdAt": now() - timedelta(minutes=4)}})
    gateway.actual = {"status": "done", "has_audio": False, "transcript": [{"role": "user", "message": "Synthetic input"}]}
    restarted = VoiceService(store.db, cases, voice.settings, gateway)
    assert restarted.reconcile_pending() == 1
    assert store.db.call_records.count_documents({"caseId": case["id"], "transcriptStatus": "saved"}) == 1
    assert restarted.reconcile_pending() == 0
    assert store.db.jobs.count_documents({}) == 0


def test_actual_provider_transcript_is_private_case_linked_and_idempotent(voice, gateway, store, cases):
    issued = voice.start("owner-1", start_request())
    state = issued["session"]
    gateway.actual = {"conversation_id": issued["conversationId"], "agent_id": "agent_controlled", "status": "done", "has_audio": False,
        "transcript": [{"role": "user", "message": "No", "time_in_call_secs": 2, "hidden_reasoning": "never store this"},
                       {"role": "agent", "message": "Which road is affected?", "time_in_call_secs": 3},
                       {"role": "system", "message": "secret instructions"}]}
    finished = voice.finish(state["id"], "owner-1")
    assert finished["transcriptStatus"] == "saved"
    assert store.db.call_records.count_documents({}) == 0
    case = draft_case(cases)
    before = deepcopy(store.db.cases.find_one({"id": case["id"]}))
    voice.bind(state["id"], "owner-1", VoiceBind(case_id=case["id"], case_version=1))
    voice.finish(state["id"], "owner-1")
    history = voice.case_history(case["id"], "owner-1")["conversations"]
    assert len(history) == 1 and history[0]["visibility"] == "private"
    assert history[0]["transcript"][0]["message"] == "No"
    assert len(history[0]["transcript"]) == 2
    assert history[0]["recording"] == {"enabled": False, "status": "disabled", "reference": None}
    assert "hidden_reasoning" not in str(history) and "ownerKey" not in history[0]
    assert store.db.cases.find_one({"id": case["id"]}) == before
    assert store.db.procedural_lessons.count_documents({}) == 0
    with pytest.raises(DomainError):
        voice.case_history(case["id"], "owner-2")


def test_link_rejects_wrong_owner_version_location_and_case_reassignment(voice, store, cases):
    state = voice.start("owner-1", start_request())["session"]
    case = draft_case(cases)
    with pytest.raises(DomainError):
        voice.bind(state["id"], "owner-2", VoiceBind(case_id=case["id"], case_version=1))
    with pytest.raises(DomainError):
        voice.bind(state["id"], "owner-1", VoiceBind(case_id=case["id"], case_version=2))
    store.db.cases.update_one({"id": case["id"]}, {"$set": {"location.incidentAddress": "Different incident"}})
    with pytest.raises(DomainError):
        voice.bind(state["id"], "owner-1", VoiceBind(case_id=case["id"], case_version=1))
    store.db.cases.update_one({"id": case["id"]}, {"$set": {"location": start_request().location.model_dump(by_alias=True)}})
    voice.bind(state["id"], "owner-1", VoiceBind(case_id=case["id"], case_version=1))
    other = draft_case(cases)
    with pytest.raises(DomainError):
        voice.bind(state["id"], "owner-1", VoiceBind(case_id=other["id"], case_version=1))
    changed = cases.patch_case(case["id"], "owner-1", CasePatch(expected_version=1, answers={"immediateDanger": "No"}))
    assert changed["version"] == 2
    with pytest.raises(DomainError):
        voice.read(state["id"], "owner-1")


def test_gateway_uses_single_use_reserved_signed_url_and_server_header():
    seen = []
    def respond(request):
        seen.append(request)
        assert request.headers["xi-api-key"] == "private-test-key"
        if "/agents/" in request.url.path:
            return httpx.Response(200, json={"platform_settings": {"auth": {"enable_auth": True}, "privacy": {"record_voice": False}},
                "conversation_config": {"conversation": {"max_duration_seconds": 180}}})
        if request.url.path.endswith("/subscription"):
            return httpx.Response(200, json={"character_count": 0, "character_limit": 10000})
        assert request.url.params["include_conversation_id"] == "true"
        return httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?conversation_id=conv_controlled_fixture&conversation_signature=secret"})
    gateway = ElevenLabsGateway(VoiceSettings(enabled=True, api_key="private-test-key", agent_id="agent_controlled"), httpx.MockTransport(respond))
    assert gateway.signed_session()["conversationId"] == "conv_controlled_fixture"
    assert all(request.url.host == "api.elevenlabs.io" for request in seen)
    assert "private-test-key" not in repr(gateway.settings)


@pytest.mark.parametrize("recording,credits,url", [
    (True, 10000, "wss://api.elevenlabs.io/v1/convai/conversation?conversation_id=conv_controlled_fixture"),
    (False, 0, "wss://api.elevenlabs.io/v1/convai/conversation?conversation_id=conv_controlled_fixture"),
    (False, 10000, "wss://other.example/conversation?conversation_id=conv_controlled_fixture"),
    (False, 10000, "wss://api.elevenlabs.io/v1/convai/conversation?conversation_signature=secret"),
])
def test_gateway_rejects_unsafe_or_unscoped_configuration(recording, credits, url):
    def respond(request):
        if "/agents/" in request.url.path:
            return httpx.Response(200, json={"platform_settings": {"auth": {"enable_auth": True}, "privacy": {"record_voice": recording}},
                "conversation_config": {"conversation": {"max_duration_seconds": 180}}})
        if request.url.path.endswith("/subscription"):
            return httpx.Response(200, json={"character_count": 0, "character_limit": credits})
        return httpx.Response(200, json={"signed_url": url})
    gateway = ElevenLabsGateway(VoiceSettings(enabled=True, api_key="private-test-key", agent_id="agent_controlled"), httpx.MockTransport(respond))
    with pytest.raises(DomainError) as error:
        gateway.signed_session()
    assert error.value.status == 503 and "secret" not in error.value.message


def test_gateway_rejects_other_provider_conversation():
    gateway = ElevenLabsGateway(VoiceSettings(agent_id="agent_controlled"), httpx.MockTransport(lambda _: httpx.Response(200,
        json={"conversation_id": "conv_controlled_fixture", "agent_id": "agent_someone_else"})))
    with pytest.raises(DomainError):
        gateway.conversation("conv_controlled_fixture")
