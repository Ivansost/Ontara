from __future__ import annotations

import hashlib
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from .catalogue import CATALOGUE_VERSION, DEMO_LOCATIONS, FOLLOW_UP_QUESTIONS, GRAFFITI_ISSUES, NODES, QUESTIONS, ROAD_ISSUES
from .config import Settings
from .models import (ApprovalRequest, CaseCreate, CaseEventInput, CasePatch, FollowUpAnswer,
                     FollowUpInspectionRequest, FollowUpRequest, IncidentLocation, LeaseRequest, OperationTransition, ReceiptRecord)
from .research import digest_json
from .storage import Store, document, identifier, now, redact


class DomainError(Exception):
    def __init__(self, status: int, message: str, *, details: Any = None):
        self.status, self.message, self.details = status, message, details
        super().__init__(message)


def validate_answers(issue_id: str, answers: dict, *, require_all: bool = False, follow_up: list[str] | None = None) -> list[str]:
    schema = QUESTIONS.get(issue_id)
    if not schema:
        raise DomainError(422, "This issue is not available for report intake")
    questions = {q["id"]: q for q in schema["questions"]}
    questions.update({key: FOLLOW_UP_QUESTIONS[key] for key in (follow_up or []) if key in FOLLOW_UP_QUESTIONS})
    questions.update({key: FOLLOW_UP_QUESTIONS[key] for key in answers if key in FOLLOW_UP_QUESTIONS})
    unknown = set(answers) - set(questions) - set(FOLLOW_UP_QUESTIONS)
    if unknown:
        raise DomainError(422, "Unknown answer IDs", details=sorted(unknown))
    missing = []
    for key, question in questions.items():
        condition = question.get("visibleWhen")
        if condition and answers.get(condition["questionId"]) != condition["equals"]:
            continue
        value = answers.get(key)
        if value is None or value == "":
            if question["required"]:
                missing.append(key)
            continue
        if not isinstance(value, str):
            raise DomainError(422, f"Answer {key} must be text")
        if len(value) > question.get("maxLength", 2000) or len(value.strip()) < question.get("minLength", 0):
            raise DomainError(422, f"Answer {key} has an invalid length")
        if question["type"] == "select" and value not in {o["value"] for o in question["options"]}:
            raise DomainError(422, f"Answer {key} is not an allowed choice")
        if question["type"] == "date":
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise DomainError(422, f"Answer {key} must be a calendar date") from exc
    if require_all and missing:
        raise DomainError(422, "Complete the required questions before approval", details=missing)
    return missing


class CaseService:
    def __init__(self, store: Store, settings: Settings):
        self.store, self.db, self.settings = store, store.db, settings

    def route_preview(self, issue_id: str, location: IncidentLocation, answers: dict | None = None) -> dict:
        answers = answers or {}
        item = NODES.get(issue_id)
        if not item or item["kind"] != "issue" or not item["available"]:
            return {"supported": False, "reason": "This service is not available in the demo; no report or personal details are saved.", "route": None, "missingAnswers": [], "urgentHandoff": False, "demo": True}
        missing = validate_answers(issue_id, answers)
        urgent = any(option.get("urgentHandoff") and answers.get(question["id"]) == option["value"]
                     for question in QUESTIONS[issue_id]["questions"] for option in question.get("options", []))
        if urgent:
            return {"supported": False, "reason": "Stay clear of the hazard. Immediate danger or a critical traffic control needs urgent local assistance; use emergency services for an immediate threat.", "route": None, "missingAnswers": missing, "urgentHandoff": True, "demo": True}
        if not location.confirmed:
            return {"supported": False, "reason": "Confirm the incident location before choosing a recipient.", "route": None, "missingAnswers": missing, "urgentHandoff": False, "demo": True}
        if location.municipality_id != "milton-town" or location.upper_tier_id != "halton-region":
            return {"supported": False, "reason": "This location has no tested submission integration. Published municipal knowledge is research coverage, not live submission support.", "route": None, "missingAnswers": missing, "urgentHandoff": False, "demo": True}
        fixture = next((f for f in DEMO_LOCATIONS if f["fixtureId"] == location.fixture_id), None)
        normalize_address = lambda value: " ".join(value.casefold().split())
        if not fixture or normalize_address(location.incident_address) != normalize_address(fixture["incidentAddress"]):
            return {"supported": False, "reason": "The incident address does not match the selected controlled demo fixture. Confirm the configured fixture or use a manual authority handoff; ownership is not guessed.", "route": None, "missingAnswers": missing, "urgentHandoff": False, "demo": True}
        if issue_id in ROAD_ISSUES and location.fixture_id == "halton-regional-road":
            route = self._route("roads")
            knowledge = self._knowledge(issue_id, "halton-region")
            route["knowledgeStatus"] = knowledge["status"]
            route["knowledgeReason"] = knowledge.get("reason", "")
            route["retrievalEvidence"] = knowledge.get("evidence", {})
            if knowledge.get("selected"):
                route["publishedProcedure"] = knowledge["selected"]
                route["sources"] += knowledge["selected"]["sourceRefs"]
        elif issue_id == "graffiti-wall" and location.fixture_id == "milton-public-wall":
            route = self._route("graffiti")
            route["knowledgeStatus"] = "synthetic_demo"
        else:
            return {"supported": False, "reason": "Asset ownership or a tested receiving procedure is not established for this choice. Use the configured demo fixture or a manual authority handoff.", "route": None, "missingAnswers": missing, "urgentHandoff": False, "demo": True}
        return {"supported": True, "reason": route["reason"], "route": route, "missingAnswers": missing, "urgentHandoff": False, "demo": True}

    def _route(self, portal_id: str) -> dict:
        roads = portal_id == "roads"
        authority = "halton-region" if roads else "milton-town"
        return {"id": "halton-roads-demo" if roads else "milton-graffiti-demo", "authorityId": authority,
                "portalId": portal_id, "procedureId": "demo-halton-roads-v1" if roads else "demo-milton-graffiti-v1",
                "recipient": {"id": authority, "name": "Regional Roads Portal — DEMO" if roads else "Local Municipality Portal — DEMO",
                              "portalId": portal_id, "portalUrl": f"{self.settings.portal_base_url}/portals/{portal_id}/new"},
                "reason": "This synthetic incident fixture has an explicit controlled-demo owner profile. Your residence does not decide responsibility.",
                "sources": [{"title": "Controlled synthetic demo routing profile", "url": f"{self.settings.portal_base_url}/portals/{portal_id}/new"}],
                "demo": True, "integrationStatus": "demo_configured"}

    def _knowledge(self, issue_id: str, authority_id: str) -> dict:
        """Native retrieval narrows published knowledge; it never grants live contact."""
        try:
            from .retrieval import retrieve_procedures
        except ImportError:
            return {"status": "pending", "reason": "Required native procedure retrieval is not yet available", "evidence": {"nativeQuery": False}}
        if not hasattr(self, "db"):
            return {"status": "pending", "reason": "Atlas must be ready to verify published procedures", "evidence": {"nativeQuery": False}}
        # Curated issue text avoids placing resident narratives into shared knowledge.
        query = f"Published reporting instructions, responsibility and required facts for {NODES[issue_id]['label']} on a Halton regional road"
        try:
            result = retrieve_procedures(self.db, query, authority_id, issue_id)
        except Exception as exc:
            return {"status": "assistance_required", "reason": "Required native procedure lookup is unavailable", "evidence": {"nativeQuery": False, "errorType": type(exc).__name__}}
        if result["status"] != "ready":
            return result
        for candidate in result.get("candidates", []):
            if candidate.get("authorityId") != authority_id or issue_id not in candidate.get("issueIds", []) or candidate.get("verificationStatus") != "verified":
                continue
            references = []
            for source_id in candidate.get("sourceIds", []):
                source = self.db.source_references.find_one({"id": source_id, "verificationStatus": "verified"})
                if source:
                    references.append({"id": source["id"], "sourceVersion": source["sourceVersion"], "title": source["title"], "url": source["url"]})
            if references:
                return {**result, "selected": {"id": candidate["id"], "sourceVersion": candidate["sourceVersion"],
                    "title": candidate["title"], "authorityId": authority_id, "verificationStatus": "verified",
                    "integrationStatus": candidate["integrationStatus"], "sourceRefs": references}}
        return {**result, "status": "assistance_required", "reason": "Retrieved knowledge has no valid official source provenance"}

    def create_case(self, owner: str, request: CaseCreate) -> dict:
        route = self.route_preview(request.issue_id, request.location, request.answers)
        if not route["supported"]:
            raise DomainError(422, route["reason"])
        stamp = now()
        case_id = identifier("case")
        case = {"id": case_id, "ownerKey": owner, "version": 1, "issueId": request.issue_id,
                "location": request.location.model_dump(by_alias=True), "answers": request.answers,
                "reporter": request.reporter.model_dump(by_alias=True) if request.reporter else None,
                "route": route["route"], "stage": "draft", "approvedVersion": None,
                "currentOperationId": None, "pendingQuestionIds": [], "receipt": None,
                "createdAt": stamp, "updatedAt": stamp, "cancelledAt": None, "runId": identifier("run")}
        case["questionnaireVersion"] = CATALOGUE_VERSION
        with self.store.atomic() as kw:
            self.db.cases.insert_one(deepcopy(case), **kw)
            self._save_version(case, kw)
            self._event(case_id, "draft_saved", "Report draft saved in your private session.", kw=kw)
            if case["route"].get("retrievalEvidence"):
                self._event(case_id, "procedure_retrieved", "Retrieved source-backed published procedure for the configured demo authority.",
                            data={"publishedProcedure": case["route"].get("publishedProcedure"), **case["route"]["retrievalEvidence"]}, visibility="presenter", kw=kw)
        return self._view(case)

    def get_case(self, case_id: str, owner: str) -> dict:
        return self._view(self._owned(case_id, owner))

    def get_case_internal(self, case_id: str) -> dict:
        item = self.db.cases.find_one({"id": case_id})
        if not item:
            raise DomainError(404, "Case not found")
        return self._view(item)

    def get_operation_internal(self, operation_id: str) -> dict:
        item = self.db.operations.find_one({"id": operation_id})
        if not item:
            raise DomainError(404, "Operation not found")
        return document(item)

    def get_version_internal(self, case_id: str, version: int) -> dict:
        item = self.db.case_versions.find_one({"caseId": case_id, "version": version})
        if not item:
            raise DomainError(404, "Case version not found")
        return document(item)

    def patch_case(self, case_id: str, owner: str, request: CasePatch) -> dict:
        with self.store.atomic() as kw:
            case = self._owned(case_id, owner, kw)
            self._editable(case, request.expected_version, kw)
            updated = deepcopy(case)
            if request.location is not None:
                updated["location"] = request.location.model_dump(by_alias=True)
            if request.answers is not None:
                validate_answers(case["issueId"], request.answers, follow_up=case.get("pendingQuestionIds"))
                updated["answers"] = request.answers
            if request.reporter is not None:
                updated["reporter"] = request.reporter.model_dump(by_alias=True)
            decision = self.route_preview(case["issueId"], IncidentLocation.model_validate(updated["location"]), updated["answers"])
            if not decision["supported"]:
                raise DomainError(422, decision["reason"])
            updated["route"] = decision["route"]
            updated["questionnaireVersion"] = CATALOGUE_VERSION
            if self._payload(updated) == self._payload(case):
                return self._view(case)
            updated.update(version=case["version"] + 1, approvedVersion=None, stage="draft", updatedAt=now(), currentOperationId=None)
            self._replace_case(case, updated, kw)
            self._save_version(updated, kw)
            self._stop_queued(case_id, "Report changed; prior approval is no longer valid.", kw)
            self._event(case_id, "report_edited", "Report edited. Review and approve the new version before it is sent.", kw=kw)
            return self._view(updated)

    def approve(self, case_id: str, owner: str, request: ApprovalRequest) -> dict:
        with self.store.atomic() as kw:
            case = self._owned(case_id, owner, kw)
            if case["cancelledAt"]:
                raise DomainError(409, "This case has been cancelled")
            if case["version"] != request.version:
                raise DomainError(409, "The report changed. Review the current version before approving it.")
            if self._unresolved_operation(case_id, kw):
                raise DomainError(409, "An earlier submission outcome is uncertain. Reconcile it before approving further work.")
            if case.get("approvedVersion") == request.version and case.get("currentOperationId"):
                return self._view(case)
            action = "update" if case.get("receipt") else "create"
            existing = self.db.operations.find_one({"caseId": case_id, "caseVersion": request.version, "action": action}, **kw)
            if existing:
                return self._view(case)
            decision = self.route_preview(case["issueId"], IncidentLocation.model_validate(case["location"]), case["answers"])
            if not decision["supported"]:
                raise DomainError(422, decision["reason"])
            if case["route"]["portalId"] == "roads":
                if decision["route"].get("knowledgeStatus") != "ready":
                    raise DomainError(409, "Required native procedure retrieval is pending or unavailable. Submission has not been authorized.")
                if decision["route"].get("publishedProcedure") != case["route"].get("publishedProcedure"):
                    raise DomainError(409, "Published routing knowledge changed. Save and review the current report before approving it.")
            validate_answers(case["issueId"], case["answers"], require_all=True, follow_up=case.get("pendingQuestionIds"))
            if not case.get("reporter") or not case["reporter"].get("contactConsent"):
                # Contact is optional; consent is required only if contact details are included.
                if case.get("reporter") and (case["reporter"].get("name") or case["reporter"].get("email")):
                    raise DomainError(422, "Approve sharing your contact details or remove them")
            payload = self._payload(case)
            payload_digest = digest_json(payload)
            operation_id = "op_" + hashlib.sha256(f"{case_id}:{case['version']}:{action}:{case['route']['recipient']['id']}".encode()).hexdigest()[:32]
            stamp = now()
            pending_fault = case.get("pendingCreateFault") or {}
            transfer_fault = action == "create" and pending_fault.get("armed") is True and not pending_fault.get("consumedAt")
            if transfer_fault and case["route"].get("demo") is not True:
                raise DomainError(409, "A presenter fault is restricted to a supported controlled demo case")
            operation = {"id": operation_id, "clientReference": operation_id, "caseId": case_id,
                         "caseVersion": case["version"], "runId": case["runId"], "action": action,
                         "portalId": case["route"]["portalId"], "recipientId": case["route"]["recipient"]["id"],
                         "route": case["route"], "payload": payload, "payloadDigest": payload_digest,
                         "state": "prepared", "receipt": None, "createdAt": stamp, "updatedAt": stamp,
                         "externalTicketId": (case.get("receipt") or {}).get("ticketId"),
                         "updateUrl": (case.get("receipt") or {}).get("updateUrl"), "faultPlan": {
                             "kind": "kill_after_acceptance", "armed": True, "armedAt": pending_fault.get("armedAt"),
                             "scope": "case_next_create", "caseId": case_id,
                         } if transfer_fault else None}
            self.db.operations.insert_one(operation, **kw)
            self.db.jobs.insert_one({"id": f"job_{operation_id}", "operationId": operation_id, "caseId": case_id,
                                     "kind": "execute_operation", "readOnly": False, "state": "queued", "attempt": 0, "fence": 0, "createdAt": stamp,
                                     "updatedAt": stamp, "leaseUntil": stamp}, **kw)
            case_updates = {
                "approvedVersion": case["version"], "currentOperationId": operation_id, "stage": "preparing_report",
                "updatedAt": stamp, "pendingQuestionIds": [],
            }
            if transfer_fault:
                case_updates.update({"pendingCreateFault.armed": False, "pendingCreateFault.consumedAt": stamp,
                                     "pendingCreateFault.operationId": operation_id})
            result = self.db.cases.update_one({"id": case_id, "version": case["version"], "cancelledAt": None}, {"$set": case_updates}, **kw)
            if result.modified_count != 1:
                raise DomainError(409, "The report changed during approval")
            self._event(case_id, "report_approved", "You approved this report version and its named recipient.", operation_id=operation_id, data={"version": case["version"], "action": action}, kw=kw)
            return self._view(self.db.cases.find_one({"id": case_id}, **kw))

    def answer_follow_up(self, case_id: str, owner: str, request: FollowUpAnswer) -> dict:
        case = self._owned(case_id, owner)
        pending = case.get("pendingQuestionIds", [])
        if not pending or not set(request.answers).issubset(pending):
            raise DomainError(422, "Answer only the pending authored follow-up questions")
        return self.patch_case(case_id, owner, CasePatch(expectedVersion=request.expected_version, answers={**case["answers"], **request.answers}))

    def request_follow_up(self, case_id: str, request: FollowUpRequest) -> dict:
        if not set(request.question_ids).issubset(FOLLOW_UP_QUESTIONS):
            raise DomainError(422, "Follow-up question is not in the authored question bank")
        with self.store.atomic() as kw:
            case = self.db.cases.find_one({"id": case_id}, **kw)
            if not case:
                raise DomainError(404, "Case not found")
            if case["cancelledAt"]:
                raise DomainError(409, "This case has been cancelled")
            dedupe = f"followup:{case_id}:{request.source_event_id}"
            if self.db.case_events.find_one({"dedupeKey": dedupe}, **kw):
                return self._view(case)
            if not case.get("receipt"):
                raise DomainError(409, "A verified report receipt is required before follow-up")
            if request.external_ticket_id and request.external_ticket_id != case["receipt"]["ticketId"]:
                raise DomainError(422, "Follow-up ticket does not match this case")
            pending = list(dict.fromkeys(case.get("pendingQuestionIds", []) + request.question_ids))
            self.db.cases.update_one({"id": case_id}, {"$set": {"pendingQuestionIds": pending, "stage": "more_information_needed", "updatedAt": now()}}, **kw)
            self._event(case_id, "more_information_requested", request.reason, operation_id=request.operation_id,
                        data={"questionIds": request.question_ids, "sourceEventId": request.source_event_id}, dedupe_key=dedupe, kw=kw)
            return self._view(self.db.cases.find_one({"id": case_id}, **kw))

    def request_follow_up_inspection(self, case_id: str, request: FollowUpInspectionRequest) -> dict:
        with self.store.atomic() as kw:
            case = self.db.cases.find_one({"id": case_id}, **kw)
            operation = self.db.operations.find_one({"id": request.operation_id, "caseId": case_id, "state": "receipt_verified"}, **kw)
            if not case or not operation:
                raise DomainError(404, "Verified case operation not found")
            if case.get("cancelledAt"):
                raise DomainError(409, "This case has been cancelled")
            if (operation.get("receipt") or {}).get("ticketId") != request.external_ticket_id:
                raise DomainError(422, "Inspection must refer to this operation's verified ticket")
            job_id = "inspection_" + hashlib.sha256(f"{case_id}:{request.source_event_id}".encode()).hexdigest()[:32]
            existing = self.db.jobs.find_one({"id": job_id}, **kw)
            if existing:
                return document(existing)
            stamp = now()
            job = {"id": job_id, "caseId": case_id, "operationId": operation["id"], "kind": "follow_up_inspection",
                   "readOnly": True, "sourceEventId": request.source_event_id, "reason": request.reason,
                   "withholdLessonIds": request.withhold_lesson_ids,
                   "externalTicketId": request.external_ticket_id, "state": "queued", "attempt": 0, "fence": 0,
                   "createdAt": stamp, "updatedAt": stamp, "leaseUntil": stamp}
            self.db.jobs.insert_one(job, **kw)
            self._event(case_id, "follow_up_received", "The simulated authority requested more information. Ontara is checking the current receiving form.",
                        operation_id=operation["id"], data={"sourceEventId": request.source_event_id, "inspectionJobId": job_id},
                        dedupe_key=f"inspection:{case_id}:{request.source_event_id}", kw=kw)
            return document(job)

    def inspection_result(self, job_id: str, worker_id: str, token: str, status: str, reason: str, evidence: dict) -> dict:
        with self.store.atomic() as kw:
            job = self._guard(job_id, worker_id, token, kw)
            if job.get("kind") != "follow_up_inspection" or not job.get("readOnly"):
                raise DomainError(422, "This is not a read-only inspection job")
            case = self.db.cases.find_one({"id": job["caseId"], "cancelledAt": None}, **kw)
            if not case:
                raise DomainError(409, "Case authorization was revoked")
            if status == "needs_input" and not case.get("pendingQuestionIds"):
                raise DomainError(409, "Persist the authored follow-up question before finishing the inspection")
            self.db.jobs.update_one({"id": job_id, "leaseToken": token}, {"$set": {"state": "paused" if status == "needs_assistance" else "completed", "inspectionStatus": status, "updatedAt": now()}}, **kw)
            if status == "needs_assistance":
                self.db.cases.update_one({"id": case["id"]}, {"$set": {"stage": "needs_assistance", "updatedAt": now()}}, **kw)
            self._event(case["id"], "form_inspected", reason, operation_id=job["operationId"], visibility="presenter", data={**evidence, "inspectionStatus": status, "jobId": job_id}, kw=kw)
            return {"jobId": job_id, "status": status, "readOnly": True}

    def cancel(self, case_id: str, owner: str, reason: str | None = None) -> dict:
        with self.store.atomic() as kw:
            case = self._owned(case_id, owner, kw)
            if case["cancelledAt"]:
                return self._view(case)
            unresolved = self._unresolved_operation(case_id, kw)
            stamp = now()
            self.db.cases.update_one({"id": case_id}, {"$set": {"cancelledAt": stamp, "stage": "cancelled", "approvedVersion": None, "updatedAt": stamp}}, **kw)
            self.db.jobs.update_many({"caseId": case_id, "state": {"$in": ["queued", "leased"]}}, {"$set": {"state": "cancelled", "updatedAt": stamp}}, **kw)
            self.db.operations.update_many({"caseId": case_id, "state": "prepared"}, {"$set": {"state": "stopped", "updatedAt": stamp}}, **kw)
            message = ("Future actions stopped. An earlier submission attempt remains unverified; cancellation does not establish that it was not accepted."
                       if unresolved else "Future actions stopped. Cancellation cannot undo a report already accepted by the receiving portal.")
            self._event(case_id, "case_cancelled", message, data={"reason": reason, "outcomeUncertain": bool(unresolved),
                        "unresolvedOperationId": unresolved["id"] if unresolved else None}, kw=kw)
            return self._view(self.db.cases.find_one({"id": case_id}, **kw))

    def timeline(self, case_id: str, owner: str) -> dict:
        self._owned(case_id, owner)
        events = self.db.case_events.find({"caseId": case_id, "visibility": "resident"}).sort("createdAt", 1)
        return {"events": [document(e) for e in events]}

    def presenter_evidence(self, case_id: str) -> dict:
        return {"case": self.get_case_internal(case_id),
                "operations": [redact(document(x)) for x in self.db.operations.find({"caseId": case_id})],
                "events": [redact(document(x)) for x in self.db.execution_events.find({"caseId": case_id}).sort("createdAt", 1)]}

    def lease_job(self, request: LeaseRequest) -> dict:
        stamp = now()
        query: dict = {"$or": [{"state": "queued"}, {"state": "leased", "leaseUntil": {"$lte": stamp}}]}
        if request.job_id:
            query["id"] = request.job_id
        if request.case_id:
            query["caseId"] = request.case_id
        with self.store.atomic() as kw:
            job = self.db.jobs.find_one_and_update(query, {"$set": {"state": "leased", "workerId": request.worker_id,
                "leaseToken": secrets.token_urlsafe(32), "leaseUntil": stamp + timedelta(seconds=request.lease_seconds), "updatedAt": stamp},
                "$inc": {"attempt": 1, "fence": 1}}, sort=[("createdAt", 1)], return_document=ReturnDocument.AFTER, **kw)
            if not job:
                return {"job": None}
            case = self.db.cases.find_one({"id": job["caseId"]}, **kw)
            operation = self.db.operations.find_one({"id": job["operationId"]}, **kw)
            readonly = job.get("kind") == "follow_up_inspection" and job.get("readOnly") is True
            valid_authorization = operation and (operation["state"] == "receipt_verified" if readonly else case and case.get("approvedVersion") == operation["caseVersion"])
            if not case or not operation or case.get("cancelledAt") or not valid_authorization:
                self.db.jobs.update_one({"id": job["id"]}, {"$set": {"state": "cancelled"}}, **kw)
                return {"job": None}
            fault = operation.get("faultPlan") or {}
            fire_fault = fault.get("armed") is True and operation["state"] == "prepared"
            job["faultAfterAcceptance"] = fire_fault
            if fire_fault:
                job["faultToken"] = secrets.token_urlsafe(16)
                self.db.operations.update_one({"id": operation["id"], "faultPlan.armed": True}, {"$set": {"faultPlan.armed": False, "faultPlan.consumedAt": stamp, "faultPlan.attempt": job["attempt"]}}, **kw)
            self._event(case["id"], "worker_leased", "Execution worker claimed durable work.", operation_id=operation["id"], visibility="presenter",
                        data={"workerId": request.worker_id, "attempt": job["attempt"], "fence": job["fence"], "faultAfterAcceptance": fire_fault}, kw=kw)
            return {"job": document(job), "case": self._view(case), "operation": document(operation),
                    "approvedVersion": document(self.db.case_versions.find_one({"caseId": case["id"], "version": operation["caseVersion"]}, **kw))}

    def heartbeat(self, job_id: str, worker_id: str, token: str, seconds: int) -> dict:
        stamp = now()
        result = self.db.jobs.find_one_and_update(self._guard_query(job_id, worker_id, token, stamp),
            {"$set": {"leaseUntil": stamp + timedelta(seconds=seconds), "updatedAt": stamp}}, return_document=ReturnDocument.AFTER)
        if not result:
            raise DomainError(409, "Lease is expired, revoked or owned by another worker")
        return document(result)

    def abandon(self, job_id: str, worker_id: str, token: str, evidence: dict) -> dict:
        with self.store.atomic() as kw:
            job = self._guard(job_id, worker_id, token, kw)
            self.db.jobs.update_one({"id": job_id, "leaseToken": token}, {"$set": {"state": "queued", "leaseUntil": now(), "updatedAt": now()}, "$unset": {"leaseToken": "", "workerId": ""}}, **kw)
            self._event(job["caseId"], "worker_process_exited", "Execution process exited; unresolved work will be reconciled by a fresh process.", operation_id=job["operationId"], visibility="presenter", data=evidence, kw=kw)
            return {"requeued": True, "operationId": job["operationId"]}

    def transition(self, operation_id: str, request: OperationTransition) -> dict:
        allowed = {"prepared": {"dispatch_started", "stopped", "needs_assistance"}, "dispatch_started": {"outcome_unknown", "reconciling", "needs_assistance"},
                   "outcome_unknown": {"reconciling", "needs_assistance"}, "reconciling": {"prepared", "needs_assistance"},
                   "needs_assistance": {"reconciling"}}
        with self.store.atomic() as kw:
            job = self._guard(request.job_id, request.worker_id, request.lease_token, kw)
            operation, case = self._authorized_operation(operation_id, job, kw)
            if operation["state"] != request.expected_state:
                raise DomainError(409, "Operation state changed; reload before acting")
            if request.state not in allowed.get(operation["state"], set()):
                raise DomainError(422, "Invalid operation transition; a verified receipt uses the receipt endpoint")
            if request.state == "prepared" and not request.evidence.get("safeNonApplicationEvidence"):
                raise DomainError(422, "Authoritative non-application evidence is required before retry")
            stamp = now()
            updates = {"state": request.state, "updatedAt": stamp, "lastAttemptId": request.attempt_id, "lastRunId": request.run_id}
            if request.state == "dispatch_started":
                updates.update({"dispatchStartedAt": operation.get("dispatchStartedAt") or stamp,
                                "lastDispatchStartedAt": stamp, "outcomeUncertain": True})
            elif request.state == "prepared":
                updates.update({"outcomeUncertain": False, "nonApplicationEstablishedAt": stamp,
                                "safeNonApplicationEvidence": redact(request.evidence["safeNonApplicationEvidence"])})
            self.db.operations.update_one({"id": operation_id, "state": request.expected_state}, {"$set": updates}, **kw)
            stage = "checking_submission" if request.state in {"dispatch_started", "outcome_unknown", "reconciling"} else "needs_assistance" if request.state == "needs_assistance" else "preparing_report"
            if request.state == "needs_assistance" and case.get("pendingQuestionIds"):
                stage = "more_information_needed"
            self.db.cases.update_one({"id": case["id"]}, {"$set": {"stage": stage, "updatedAt": now()}}, **kw)
            if request.state == "needs_assistance":
                self.db.jobs.update_one({"id": job["id"]}, {"$set": {"state": "paused", "updatedAt": now()}}, **kw)
            self._event(case["id"], request.state, "Checking receiving-system evidence." if stage == "checking_submission" else "Execution state updated.", operation_id=operation_id,
                        data={**request.evidence, "runId": request.run_id, "attemptId": request.attempt_id}, visibility="presenter", kw=kw)
            return document(self.db.operations.find_one({"id": operation_id}, **kw))

    def record_receipt(self, operation_id: str, request: ReceiptRecord) -> dict:
        with self.store.atomic() as kw:
            job = self._guard(request.job_id, request.worker_id, request.lease_token, kw)
            operation, case = self._authorized_operation(operation_id, job, kw)
            receipt = request.receipt.model_dump(by_alias=True)
            expected = {"clientReference": operation["id"], "payloadDigest": operation["payloadDigest"], "portalId": operation["portalId"], "action": operation["action"], "runId": operation["runId"]}
            if any(receipt.get(key) != value for key, value in expected.items()):
                raise DomainError(422, "Receipt does not match the approved operation")
            if receipt.get("authorityId") and receipt["authorityId"] != operation["route"]["authorityId"]:
                raise DomainError(422, "Receipt authority does not match the approved recipient")
            if receipt.get("routeId") and receipt["routeId"] != operation["route"]["id"]:
                raise DomainError(422, "Receipt route does not match the approved destination")
            if operation["externalTicketId"] and receipt["ticketId"] != operation["externalTicketId"]:
                raise DomainError(422, "Follow-up receipt belongs to a different ticket")
            if operation["state"] not in {"dispatch_started", "outcome_unknown", "reconciling", "receipt_verified"}:
                raise DomainError(409, "Dispatch or reconciliation must precede receipt recording")
            if operation.get("receipt") and operation["receipt"] != receipt:
                raise DomainError(409, "A different receipt is already attached")
            self.db.operations.update_one({"id": operation_id}, {"$set": {"state": "receipt_verified", "receipt": receipt, "outcomeUncertain": False, "outcomeResolvedAt": now(), "updatedAt": now()}}, **kw)
            self.db.jobs.update_one({"id": job["id"]}, {"$set": {"state": "completed", "updatedAt": now()}}, **kw)
            self.db.cases.update_one({"id": case["id"]}, {"$set": {"receipt": receipt, "stage": "report_acknowledged", "updatedAt": now()}}, **kw)
            self._event(case["id"], "receipt_verified", "Report acknowledged by the controlled demo portal." if operation["action"] == "create" else "Follow-up received by the same controlled demo ticket.",
                        operation_id=operation_id, data={"ticketId": receipt["ticketId"], "receiptId": receipt["receiptId"], "action": operation["action"]}, dedupe_key=f"receipt:{operation_id}", kw=kw)
            return {"case": self._view(self.db.cases.find_one({"id": case["id"]}, **kw)), "operation": document(self.db.operations.find_one({"id": operation_id}, **kw)), "receipt": receipt}

    def arm_fault(self, operation_id: str, armed: bool) -> dict:
        with self.store.atomic() as kw:
            operation = self.db.operations.find_one({"id": operation_id}, **kw)
            if not operation:
                raise DomainError(404, "Operation not found")
            if operation["state"] != "prepared" or operation["action"] != "create" or operation["route"].get("demo") is not True:
                raise DomainError(409, "A fault can only be armed for a prepared controlled-demo create operation")
            if (operation.get("faultPlan") or {}).get("consumedAt"):
                raise DomainError(409, "This operation's one-shot fault has already been consumed")
            if self.db.jobs.find_one({"operationId": operation_id, "state": "leased", "leaseUntil": {"$gt": now()}}, **kw):
                raise DomainError(409, "This operation is already leased; arm the draft before approval")
            plan = {**(operation.get("faultPlan") or {}), "armed": armed, "kind": "kill_after_acceptance"}
            result = self.db.operations.update_one({"id": operation_id, "state": "prepared", "faultPlan.consumedAt": {"$exists": False}},
                {"$set": {"faultPlan": plan, "updatedAt": now()}}, **kw)
            if not result.matched_count:
                raise DomainError(409, "The fault state changed before it could be armed")
            return {"operationId": operation_id, "armed": armed}

    def arm_next_create_fault(self, case_id: str, armed: bool) -> dict:
        with self.store.atomic() as kw:
            case = self.db.cases.find_one({"id": case_id}, **kw)
            if not case:
                raise DomainError(404, "Case not found")
            if (case.get("pendingCreateFault") or {}).get("consumedAt"):
                raise DomainError(409, "This case's one-shot create fault has already been consumed")
            if case.get("cancelledAt") or case.get("receipt") or case["stage"] != "draft" or case.get("approvedVersion") is not None or case.get("currentOperationId"):
                raise DomainError(409, "Arm the next create fault only while the case is an unapproved draft")
            if case["route"].get("demo") is not True or self.db.operations.find_one({"caseId": case_id}, **kw):
                raise DomainError(409, "Fault arming is restricted to an unused supported controlled demo case")
            decision = self.route_preview(case["issueId"], IncidentLocation.model_validate(case["location"]), case["answers"])
            if not decision["supported"] or decision["route"].get("demo") is not True:
                raise DomainError(409, "This case has no supported controlled demo route")
            plan = {"kind": "kill_after_acceptance", "armed": armed,
                    "armedAt": (case.get("pendingCreateFault") or {}).get("armedAt") or now()}
            result = self.db.cases.update_one({"id": case_id, "version": case["version"], "approvedVersion": None, "currentOperationId": None,
                                              "cancelledAt": None, "stage": "draft", "pendingCreateFault.consumedAt": {"$exists": False}},
                                             {"$set": {"pendingCreateFault": plan}}, **kw)
            if not result.matched_count:
                raise DomainError(409, "The draft changed before the fault could be armed")
            self._event(case_id, "presenter_fault_armed" if armed else "presenter_fault_disarmed",
                        "Presenter one-shot crash control configured for the next approved create operation.",
                        data={"kind": plan["kind"], "armed": armed}, visibility="presenter", kw=kw)
            return {"caseId": case_id, "kind": plan["kind"], "armed": armed, "appliesTo": "next_create"}

    def add_event(self, case_id: str, event: CaseEventInput) -> dict:
        self.get_case_internal(case_id)
        return self._event(case_id, event.kind, event.message, operation_id=event.operation_id,
                           visibility=event.visibility, data={**event.data, "runId": event.run_id, "attemptId": event.attempt_id})

    def _guard_query(self, job_id: str, worker_id: str, token: str, stamp: datetime) -> dict:
        return {"id": job_id, "workerId": worker_id, "leaseToken": token, "state": "leased", "leaseUntil": {"$gt": stamp}}

    def _guard(self, job_id: str, worker_id: str, token: str, kw: dict) -> dict:
        job = self.db.jobs.find_one(self._guard_query(job_id, worker_id, token, now()), **kw)
        if not job:
            raise DomainError(409, "Lease is expired, revoked or owned by another worker")
        return job

    def _authorized_operation(self, operation_id: str, job: dict, kw: dict) -> tuple[dict, dict]:
        if job["operationId"] != operation_id:
            raise DomainError(403, "Job does not authorize this operation")
        if job.get("readOnly") or job.get("kind") == "follow_up_inspection":
            raise DomainError(403, "A read-only inspection cannot authorize an external write or operation transition")
        operation = self.db.operations.find_one({"id": operation_id}, **kw)
        case = self.db.cases.find_one({"id": job["caseId"]}, **kw)
        if not operation or not case or case.get("cancelledAt") or case.get("approvedVersion") != operation["caseVersion"]:
            raise DomainError(409, "Authorization has been revoked or changed")
        return operation, case

    def _owned(self, case_id: str, owner: str, kw: dict | None = None) -> dict:
        case = self.db.cases.find_one({"id": case_id, "ownerKey": owner}, **(kw or {}))
        if not case:
            raise DomainError(404, "Case not found in this browser session")
        return case

    def _editable(self, case: dict, version: int, kw: dict) -> None:
        if case["cancelledAt"]:
            raise DomainError(409, "This case has been cancelled")
        if case["version"] != version:
            raise DomainError(409, "The report changed. Reload before editing.")
        if self._unresolved_operation(case["id"], kw):
            raise DomainError(409, "The current submission must be reconciled before its facts can be edited")

    def _unresolved_operation(self, case_id: str, kw: dict) -> dict | None:
        active = self.db.operations.find_one({"caseId": case_id, "state": {"$in": ["dispatch_started", "outcome_unknown", "reconciling"]}}, **kw)
        if active:
            return active
        for operation in self.db.operations.find({"caseId": case_id, "state": "needs_assistance"}, **kw):
            if operation.get("outcomeUncertain") is True:
                return operation
            if "outcomeUncertain" not in operation:
                # Preserve the guard for operations created before explicit uncertainty metadata.
                dispatched = operation.get("dispatchStartedAt") or self.db.case_events.find_one({"operationId": operation["id"], "kind": "dispatch_started"}, **kw)
                if dispatched:
                    return operation
        return None

    def _replace_case(self, old: dict, updated: dict, kw: dict) -> None:
        result = self.db.cases.replace_one({"id": old["id"], "version": old["version"], "cancelledAt": None}, updated, **kw)
        if result.modified_count != 1:
            raise DomainError(409, "The report changed during this edit")

    def _stop_queued(self, case_id: str, reason: str, kw: dict) -> None:
        self.db.jobs.update_many({"caseId": case_id, "state": {"$in": ["queued", "leased", "paused"]}}, {"$set": {"state": "cancelled", "updatedAt": now()}}, **kw)
        self.db.operations.update_many({"caseId": case_id, "state": "prepared"}, {"$set": {"state": "stopped", "stopReason": reason, "updatedAt": now()}}, **kw)

    def _payload(self, case: dict) -> dict:
        payload = deepcopy({key: case[key] for key in ("issueId", "location", "answers", "reporter", "route")})
        payload["route"].pop("retrievalEvidence", None)
        payload["route"].pop("knowledgeReason", None)
        payload["questionnaireVersion"] = case.get("questionnaireVersion")
        return payload

    def _save_version(self, case: dict, kw: dict) -> None:
        payload = self._payload(case)
        questionnaire = deepcopy(QUESTIONS[case["issueId"]])
        questionnaire["questions"] += [deepcopy(FOLLOW_UP_QUESTIONS[q]) for q in case.get("pendingQuestionIds", [])]
        self.db.case_versions.insert_one({"id": f"{case['id']}:{case['version']}", "caseId": case["id"], "version": case["version"],
                                          "payload": payload, "payloadDigest": digest_json(payload), "questionnaire": questionnaire, "createdAt": now()}, **kw)

    def _view(self, case: dict) -> dict:
        result = document(case)
        result.pop("ownerKey", None)
        result["pendingQuestions"] = [deepcopy(FOLLOW_UP_QUESTIONS[q]) for q in case.get("pendingQuestionIds", [])]
        result.pop("pendingQuestionIds", None)
        result.pop("pendingCreateFault", None)
        # Signed update URLs and receipt signatures are execution capabilities, not resident data.
        if result.get("receipt"):
            result["receipt"] = {k: v for k, v in result["receipt"].items() if k not in {"updateUrl", "receiptSignature"}}
        return result

    def _event(self, case_id: str, kind: str, message: str, *, operation_id: str | None = None, data: dict | None = None,
               visibility: str = "resident", dedupe_key: str | None = None, kw: dict | None = None) -> dict:
        item = {"id": identifier("event"), "caseId": case_id, "kind": kind, "message": message,
                "operationId": operation_id, "data": redact(data or {}), "visibility": visibility, "createdAt": now()}
        if dedupe_key:
            item["dedupeKey"] = dedupe_key
        self.db.case_events.insert_one(deepcopy(item), **(kw or {}))
        if visibility == "presenter":
            self.db.execution_events.insert_one(deepcopy(item), **(kw or {}))
        return document(item)
