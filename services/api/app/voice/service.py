"""Voice is a canonical-question input buffer; it has no approval/dispatch path."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ..catalogue import get_questions
from ..research import digest_json
from ..service import CaseService, DomainError, validate_answers
from ..storage import document, identifier, now
from .models import VoiceAnswer, VoiceBind, VoiceStart
from .provider import ElevenLabsGateway, VoiceSettings


class VoiceService:
    def __init__(self, db, cases: CaseService, settings: VoiceSettings,
                 gateway: ElevenLabsGateway | None = None):
        self.db, self.cases, self.settings = db, cases, settings
        self.gateway = gateway or ElevenLabsGateway(settings)
        self.db.voice_sessions.create_index("id", unique=True)
        self.db.voice_sessions.create_index([("ownerKey", 1), ("requestId", 1)], unique=True)
        self.db.voice_sessions.create_index("conversationId", unique=True, sparse=True)
        self.db.voice_sessions.create_index([("caseId", 1), ("createdAt", 1)])
        self.db.call_records.create_index("id", unique=True)
        self.db.call_records.create_index("providerConversationId", unique=True)
        self.db.call_records.create_index([("caseId", 1), ("createdAt", 1)])

    def _owned(self, session_id: str, owner: str, *, active: bool = False) -> dict:
        session = self.db.voice_sessions.find_one({"id": session_id, "ownerKey": owner})
        if not session:
            raise DomainError(404, "Voice session not found")
        if active and (session["expiresAt"] <= now() or session.get("endedAt") or session["state"] != "issued"):
            raise DomainError(409, "This voice session has ended. Continue with the written form.")
        if active and session.get("caseId"):
            case = self.cases.get_case(session["caseId"], owner)
            if case.get("cancelledAt") or case["version"] != session["caseVersion"]:
                raise DomainError(409, "The linked report changed or was stopped. Continue with the form.")
        return session

    @staticmethod
    def _questions(session: dict) -> list[dict]:
        questionnaire = get_questions(session["issueId"])
        if not questionnaire or questionnaire["version"] != session["questionnaireVersion"]:
            raise DomainError(409, "The report questions changed. Reload the written form.")
        return questionnaire["questions"]

    @classmethod
    def _next(cls, session: dict) -> dict | None:
        for question in cls._questions(session):
            condition = question.get("visibleWhen")
            if condition and session["answers"].get(condition["questionId"]) != condition["equals"]:
                continue
            if not session["answers"].get(question["id"]) and question["id"] not in session.get("skippedQuestionIds", []):
                return question
        return None

    def snapshot(self, session: dict) -> dict:
        questions = self._questions(session)
        urgent = any(option.get("urgentHandoff") and session["answers"].get(question["id"]) == option["value"]
                     for question in questions for option in question.get("options", []))
        next_question = None if urgent else self._next(session)
        state = "urgent_handoff" if urgent else "collecting" if next_question else "ready_for_review"
        message = ("Stay clear of the hazard. Immediate danger or a critical traffic control needs urgent local assistance. Use emergency services for an immediate threat."
                   if urgent else "Review the written report and named recipient before approving. Voice cannot send or approve a report.")
        answer_lines = [f"{q['label']} {session['answers'][q['id']]}" for q in questions if session["answers"].get(q["id"])]
        review = " ".join([f"Recipient: {session['recipientName']}. Controlled demo portal.",
                            f"Incident: {session['location']['incidentAddress']}.", *answer_lines,
                            "Please check these details on the written form before approving. Nothing has been sent by voice."])
        spoken = next_question["label"] if next_question else message
        if next_question and next_question.get("description"):
            spoken += " " + next_question["description"]
        if next_question and next_question.get("options"):
            spoken += " Choose " + ", ".join(o["label"] for o in next_question["options"]) + "."
        return {"id": session["id"], "revision": session["revision"], "issueId": session["issueId"],
                "questionnaireVersion": session["questionnaireVersion"], "status": state,
                "nextQuestion": next_question, "spokenQuestion": spoken, "answers": session["answers"],
                "recipientName": session["recipientName"], "message": message,
                "reviewText": review if state == "ready_for_review" else None,
                "caseId": session.get("caseId"), "caseVersion": session.get("caseVersion"),
                "expiresAt": session["expiresAt"], "ended": bool(session.get("endedAt")),
                "transcriptStatus": session.get("transcriptStatus", "pending"), "audioRecording": False}

    def _claim_quota(self, key: str, limit: int) -> None:
        self.db.voice_daily_limits.update_one({"_id": key}, {"$setOnInsert": {"count": 0, "createdAt": now()}}, upsert=True)
        claimed = self.db.voice_daily_limits.find_one_and_update({"_id": key, "count": {"$lt": limit}},
            {"$inc": {"count": 1}}, return_document=ReturnDocument.AFTER)
        if not claimed:
            raise DomainError(429, "The demo voice session limit has been reached. Continue with the written form.")

    def start(self, owner: str, request: VoiceStart) -> dict:
        if not self.settings.configured:
            raise DomainError(503, "Voice is not enabled here. Continue with the written form.")
        questionnaire = get_questions(request.issue_id)
        if not questionnaire:
            raise DomainError(422, "This service is not available for voice intake. No personal details were saved.")
        ids = {q["id"] for q in questionnaire["questions"]}
        if set(request.answers) - ids:
            raise DomainError(422, "Voice accepts only this issue's authored answer IDs")
        validate_answers(request.issue_id, request.answers)
        decision = self.cases.route_preview(request.issue_id, request.location, request.answers)
        if not decision["supported"] or decision.get("urgentHandoff"):
            raise DomainError(422, decision["reason"])
        if self.db.voice_sessions.find_one({"ownerKey": owner, "requestId": request.request_id}):
            raise DomainError(409, "A private session was already issued for this request. Start again from the voice control.")
        day = now().strftime("%Y-%m-%d")
        self._claim_quota(f"{day}:{owner}", self.settings.owner_daily_sessions)
        self._claim_quota(f"{day}:all", self.settings.daily_sessions)
        stamp = now()
        session = {"id": identifier("voice"), "ownerKey": owner, "requestId": request.request_id,
                   "issueId": request.issue_id, "questionnaireVersion": questionnaire["version"],
                   "location": request.location.model_dump(by_alias=True), "answers": deepcopy(request.answers),
                   "recipientName": decision["route"]["recipient"]["name"], "routeId": decision["route"]["id"],
                   "revision": 1, "skippedQuestionIds": [], "state": "preparing", "mode": request.mode,
                   "consent": {"version": request.consent_version, "acceptedAt": stamp, "audioRecording": False},
                   "createdAt": stamp, "updatedAt": stamp, "expiresAt": stamp + timedelta(minutes=10),
                   "transcriptStatus": "pending", "caseId": None, "caseVersion": None}
        # Do not retain answers from a branch the resident has not selected.
        for question in questionnaire["questions"]:
            condition = question.get("visibleWhen")
            if condition and session["answers"].get(condition["questionId"]) != condition["equals"]:
                session["answers"].pop(question["id"], None)
        try:
            self.db.voice_sessions.insert_one(deepcopy(session))
        except DuplicateKeyError:
            raise DomainError(409, "A private session was already issued for this request") from None
        try:
            capability = self.gateway.signed_session()
        except DomainError:
            self.db.voice_sessions.update_one({"id": session["id"]}, {"$set": {"state": "unavailable", "updatedAt": now()}})
            raise
        session.update(state="issued", conversationId=capability["conversationId"])
        self.db.voice_sessions.update_one({"id": session["id"]}, {"$set": {"state": "issued", "conversationId": capability["conversationId"], "updatedAt": now()}})
        # Never persist the signed URL or any authorization capability.
        return {"session": self.snapshot(session), "signedUrl": capability["signedUrl"],
                "conversationId": capability["conversationId"], "mode": request.mode, "connectionType": "websocket"}

    def read(self, session_id: str, owner: str) -> dict:
        return self.snapshot(self._owned(session_id, owner, active=True))

    def answer(self, session_id: str, owner: str, request: VoiceAnswer) -> dict:
        session = self._owned(session_id, owner, active=True)
        if session["revision"] != request.expected_revision:
            raise DomainError(409, "The voice answers changed. Read the current question again.")
        snapshot = self.snapshot(session)
        question = snapshot["nextQuestion"]
        if snapshot["status"] != "collecting" or not question or question["id"] != request.question_id:
            raise DomainError(422, "Voice can answer only the current visible authored question")
        updated = deepcopy(session)
        if request.value is None or not request.value.strip():
            if question["required"]:
                raise DomainError(422, "This question is required. Choose an answer or continue with the form.")
            updated["skippedQuestionIds"].append(question["id"])
        else:
            updated["answers"][question["id"]] = request.value.strip()
            validate_answers(session["issueId"], updated["answers"])
        updated.update(revision=session["revision"] + 1, updatedAt=now())
        saved = self.db.voice_sessions.find_one_and_update({"id": session_id, "ownerKey": owner,
                "revision": request.expected_revision, "endedAt": {"$exists": False}, "state": "issued"},
            {"$set": {"answers": updated["answers"], "skippedQuestionIds": updated["skippedQuestionIds"],
                      "revision": updated["revision"], "updatedAt": updated["updatedAt"]}}, return_document=ReturnDocument.AFTER)
        if not saved:
            raise DomainError(409, "The voice answers changed. Read the current question again.")
        return self.snapshot(saved)

    def bind(self, session_id: str, owner: str, request: VoiceBind) -> dict:
        session = self._owned(session_id, owner)
        case = self.cases.get_case(request.case_id, owner)
        if case["version"] != request.case_version or case.get("cancelledAt"):
            raise DomainError(409, "The report changed or was stopped before voice history could be linked")
        if case["issueId"] != session["issueId"] or digest_json(case["location"]) != digest_json(session["location"]):
            raise DomainError(409, "Voice history belongs to a different issue or incident location")
        if session.get("caseId") and session["caseId"] != case["id"]:
            raise DomainError(409, "Voice history is already linked to another report")
        result = self.db.voice_sessions.find_one_and_update({"id": session_id, "ownerKey": owner,
                "caseId": {"$in": [None, case["id"]]}},
            {"$set": {"caseId": case["id"], "caseVersion": case["version"], "linkedAt": now(),
                      "caseAnswerDigest": digest_json(case["answers"]), "updatedAt": now()}}, return_document=ReturnDocument.AFTER)
        if not result:
            raise DomainError(409, "Voice history was linked concurrently")
        self._save_call_record(result)
        return {"linked": True, "caseId": case["id"], "caseVersion": case["version"], "transcriptStatus": result["transcriptStatus"]}

    def finish(self, session_id: str, owner: str) -> dict:
        session = self._owned(session_id, owner)
        self.db.voice_sessions.update_one({"id": session_id, "ownerKey": owner, "endedAt": {"$exists": False}},
            {"$set": {"endedAt": now(), "updatedAt": now()}})
        session = self._owned(session_id, owner)
        self._sync_transcript(session)
        return {"ended": True, "transcriptStatus": session["transcriptStatus"],
                "message": "Voice stopped. Check the entered answers on the form before reviewing your report."}

    def _sync_transcript(self, session: dict) -> None:
        if session.get("transcriptStatus") != "saved" and session.get("conversationId"):
            try:
                actual = self.gateway.conversation(session["conversationId"])
            except DomainError:
                return
            transcript = [{"role": turn["role"], "message": turn["message"][:8000],
                           "timeInConversationSeconds": turn.get("time_in_call_secs")}
                          for turn in actual.get("transcript", [])[:300]
                          if turn.get("role") in {"user", "agent"} and isinstance(turn.get("message"), str)]
            complete = actual.get("status") in {"done", "failed"}
            values = {"providerStatus": actual.get("status"), "transcript": transcript,
                      "transcriptStatus": "saved" if complete else "pending", "transcriptFetchedAt": now(),
                      "providerHasAudio": actual.get("has_audio") is True, "updatedAt": now()}
            self.db.voice_sessions.update_one({"id": session["id"]}, {"$set": values})
            session.update(values)
        self._save_call_record(session)

    def reconcile_pending(self, limit: int = 3) -> int:
        """Catch up after a browser closes or an API process restarts.

        This polls only our reserved provider IDs. It cannot start a conversation,
        edit a case, or dispatch anything. Checks are leased and capped per record.
        """
        stamp = now()
        query = {"state": "issued", "conversationId": {"$exists": True}, "transcriptStatus": "pending",
                 "$and": [
                     {"$or": [{"endedAt": {"$exists": True}}, {"createdAt": {"$lte": stamp - timedelta(seconds=195)}}]},
                     {"$or": [{"nextTranscriptCheckAt": {"$exists": False}}, {"nextTranscriptCheckAt": {"$lte": stamp}}]},
                     {"$or": [{"transcriptCheckAttempts": {"$exists": False}}, {"transcriptCheckAttempts": {"$lt": 24}}]},
                 ]}
        checked = 0
        for item in self.db.voice_sessions.find(query).sort("createdAt", 1).limit(max(1, min(limit, 3))):
            claimed = self.db.voice_sessions.find_one_and_update({**query, "id": item["id"]},
                {"$set": {"nextTranscriptCheckAt": stamp + timedelta(seconds=60)}, "$inc": {"transcriptCheckAttempts": 1}},
                return_document=ReturnDocument.AFTER)
            if claimed:
                self._sync_transcript(claimed)
                checked += 1
        return checked

    def _save_call_record(self, session: dict) -> None:
        # A reserved URL is not an actual conversation. Store a call record only
        # after the provider has returned a real conversation/transcript response.
        if not session.get("caseId") or not session.get("providerStatus"):
            return
        record = {"id": session["id"], "caseId": session["caseId"], "caseVersion": session["caseVersion"],
                  "ownerKey": session["ownerKey"], "provider": "elevenlabs", "channel": "browser",
                  "direction": "browser_intake", "mode": session["mode"],
                  "providerConversationId": session["conversationId"], "voiceSessionId": session["id"],
                  "status": session["providerStatus"], "consent": session["consent"],
                  "transcript": session.get("transcript", []), "transcriptStatus": session["transcriptStatus"],
                  "transcriptFetchedAt": session.get("transcriptFetchedAt"),
                  "intakeAnswerDigest": digest_json(session["answers"]), "caseAnswerDigest": session.get("caseAnswerDigest"),
                  "recording": {"enabled": False, "status": "disabled", "reference": None},
                  "visibility": "private", "startedAt": session["createdAt"], "endedAt": session.get("endedAt"), "updatedAt": now()}
        self.db.call_records.update_one({"id": session["id"]}, {"$set": record, "$setOnInsert": {"createdAt": now()}}, upsert=True)

    def case_history(self, case_id: str, owner: str) -> dict:
        self.cases.get_case(case_id, owner)
        rows = self.db.call_records.find({"caseId": case_id, "ownerKey": owner}, {"_id": 0, "ownerKey": 0}).sort("createdAt", 1)
        return {"caseId": case_id, "conversations": [document(row) for row in rows]}
