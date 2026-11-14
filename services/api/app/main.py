from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from .catalogue import DEMO_LOCATIONS, get_catalogue, get_questions
from .config import Settings
from .models import (ApprovalRequest, ArtifactUpload, Cancellation, CaseCreate, CaseEventInput,
                     CasePatch, CaseView, CatalogueView, Contract, Coordinates, FollowUpAnswer,
                     FollowUpInspectionRequest, FollowUpRequest, HeartbeatRequest, LeaseGuard, LeaseRequest,
                     OperationTransition, Questionnaire, ReceiptRecord, ResearchBatch, RouteDecision,
                     RoutePreview, TimelineView)
from .research import ResearchImporter
from .service import CaseService, DomainError
from .storage import ArtifactStore, Store, document, redact

LOGGER = logging.getLogger("ontara.api")
COOKIE = "ontara_session"
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class FaultRequest(Contract):
    kind: Literal["kill_after_acceptance"] = "kill_after_acceptance"
    armed: bool = True


class AbandonRequest(LeaseGuard):
    reason: str = "process_exit"
    exit_code: int | None = None
    process_id: int | None = None
    attempt_id: str | None = None


class InspectionResult(LeaseGuard):
    status: Literal["needs_input", "needs_assistance", "ready"]
    question_ids: list[str] = Field(default_factory=list)
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class VerifyRecordRequest(Contract):
    collection: Literal["service_procedures", "procedural_lessons"]
    id: str
    expected_source_version: str | None = None


class RetrievalRequest(Contract):
    query: str = Field(min_length=1, max_length=5000)
    authority_id: str
    issue_id: str
    category_id: Literal["roads", "graffiti"] = "roads"
    limit: int = Field(default=3, ge=1, le=3)


class LessonRetrievalRequest(RetrievalRequest):
    portal_id: str
    form_family: str
    form_version: int
    workflow_kind: str = "ticket_update"
    withhold_lesson_ids: list[str] | None = None


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database_ready = False
        app.state.database_error = None
        app.state.mail_service = None
        app.state.dispatcher = None
        try:
            current_store = store or Store.connect(settings)
            current_store.db.command("ping")
            current_store.ensure_indexes()
            app.state.store = current_store
            app.state.db = current_store.db
            app.state.case_service = CaseService(current_store, settings)
            app.state.artifact_store = ArtifactStore(current_store.db, settings.max_artifact_bytes)
            app.state.research_importer = ResearchImporter(current_store, app.state.artifact_store)
            app.state.database_ready = True
        except Exception as exc:
            # Connection exception strings can contain credential-bearing URLs.
            app.state.database_error = type(exc).__name__
            LOGGER.warning("Atlas readiness failed (%s)", type(exc).__name__)
        if app.state.database_ready:
            try:
                from .mail import create_mail_service
                app.state.mail_service = create_mail_service(app.state.db, app.state.case_service, app.state.artifact_store)
                app.state.mail_service.start()
            except ImportError:
                pass
            except Exception as exc:
                LOGGER.warning("Mail startup pending (%s)", type(exc).__name__)
            if settings.dispatch_url:
                from .dispatch import DispatchCoordinator
                app.state.dispatcher = DispatchCoordinator(app.state.db, settings, app.state.case_service)
                app.state.dispatcher.start()
        yield
        if app.state.mail_service:
            app.state.mail_service.close()
        if app.state.dispatcher:
            app.state.dispatcher.close()
        if not store and hasattr(app.state, "store"):
            app.state.store.db.client.close()

    app = FastAPI(title="Ontara Case API", version="1.0.0", lifespan=lifespan,
                  description="Private resident cases and controlled-demo execution. Published knowledge does not establish live municipal integrations.")
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

    @app.middleware("http")
    async def anonymous_session(request: Request, call_next):
        public = request.url.path.startswith("/v1/")
        fresh = False
        if public:
            token = request.cookies.get(COOKIE, "")
            if not SESSION_PATTERN.fullmatch(token):
                token, fresh = secrets.token_urlsafe(32), True
            request.state.owner_key = hashlib.sha256(token.encode()).hexdigest()
            if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
                origin = request.headers.get("origin")
                if (origin and origin not in settings.allowed_origins) or request.headers.get("sec-fetch-site") == "cross-site":
                    return JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)
        response = await call_next(request)
        if public:
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            if fresh:
                response.set_cookie(COOKIE, token, max_age=7 * 24 * 3600, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(jsonable_encoder({"detail": error.message, "details": error.details}), status_code=error.status)

    @app.exception_handler(DuplicateKeyError)
    async def duplicate_error(request: Request, error: DuplicateKeyError):
        return JSONResponse({"detail": "This action already exists. Reload the current state before continuing."}, status_code=409)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, error: PyMongoError):
        if isinstance(error, OperationFailure) and error.has_error_label("TransientTransactionError"):
            return JSONResponse({"detail": "The record changed concurrently. Reload and retry."}, status_code=409)
        LOGGER.warning("Database operation unavailable (%s)", type(error).__name__)
        return JSONResponse({"detail": "Atlas is temporarily unavailable. Your existing saved state is retained."}, status_code=503)

    def service() -> CaseService:
        if not getattr(app.state, "database_ready", False):
            raise HTTPException(503, "Atlas runtime connection is not ready")
        return app.state.case_service

    def internal(request: Request) -> None:
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {settings.internal_token}"
        if not settings.internal_token or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(401, "Internal service authentication required")

    internal_auth = [Depends(internal)]

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "service": "ontara-api", "database": "ready" if getattr(app.state, "database_ready", False) else "unavailable"}

    @app.get("/readyz")
    def readyz():
        service()
        return {"ok": True, "database": "ready", "dispatchConfigured": bool(settings.dispatch_url)}

    @app.get("/v1/session")
    def session():
        return {"sessionActive": True, "access": "anonymous-browser-session", "expiresInSeconds": 604800}

    @app.get("/v1/catalogue", response_model=CatalogueView)
    def catalogue():
        return get_catalogue()

    @app.get("/v1/questions/{issue_id}", response_model=Questionnaire)
    def questions(issue_id: str):
        result = get_questions(issue_id)
        if not result:
            raise HTTPException(404, "This service has no active intake questions")
        return result

    @app.post("/v1/locations/resolve")
    def locations(request: Coordinates):
        return {"resolved": False, "requiresConfirmation": True, "coordinates": request.model_dump(), "demoLocations": DEMO_LOCATIONS,
                "message": "Choose and confirm the incident municipality. Coordinates alone do not establish asset ownership."}

    @app.post("/v1/routes/preview", response_model=RouteDecision)
    def route_preview(request: RoutePreview):
        # Pure authored routing remains available while Atlas is reconnecting; creates do not.
        if getattr(app.state, "database_ready", False):
            return service().route_preview(request.issue_id, request.location, request.answers)
        return _preview(settings, request)

    @app.post("/v1/cases", response_model=CaseView, status_code=201)
    def create_case(request: CaseCreate, context: Request):
        return service().create_case(context.state.owner_key, request)

    @app.get("/v1/cases/{case_id}", response_model=CaseView)
    def read_case(case_id: str, context: Request):
        return service().get_case(case_id, context.state.owner_key)

    @app.patch("/v1/cases/{case_id}", response_model=CaseView)
    def edit_case(case_id: str, request: CasePatch, context: Request):
        return service().patch_case(case_id, context.state.owner_key, request)

    @app.post("/v1/cases/{case_id}/approve", response_model=CaseView)
    def approve(case_id: str, request: ApprovalRequest, context: Request):
        return service().approve(case_id, context.state.owner_key, request)

    @app.post("/v1/cases/{case_id}/follow-up", response_model=CaseView)
    def follow_up(case_id: str, request: FollowUpAnswer, context: Request):
        return service().answer_follow_up(case_id, context.state.owner_key, request)

    @app.post("/v1/cases/{case_id}/cancel", response_model=CaseView)
    def cancel(case_id: str, request: Cancellation, context: Request):
        return service().cancel(case_id, context.state.owner_key, request.reason)

    @app.get("/v1/cases/{case_id}/timeline", response_model=TimelineView)
    def timeline(case_id: str, context: Request):
        return service().timeline(case_id, context.state.owner_key)

    @app.get("/v1/cases/{case_id}/evidence")
    def resident_evidence(case_id: str, context: Request):
        service().get_case(case_id, context.state.owner_key)
        return service().presenter_evidence(case_id)

    @app.get("/internal/v1/cases/{case_id}", dependencies=internal_auth)
    def internal_case(case_id: str):
        return service().get_case_internal(case_id)

    @app.get("/internal/v1/cases/{case_id}/versions/{version}", dependencies=internal_auth)
    def internal_version(case_id: str, version: int):
        return service().get_version_internal(case_id, version)

    @app.get("/internal/v1/operations/{operation_id}", dependencies=internal_auth)
    def internal_operation(operation_id: str):
        return service().get_operation_internal(operation_id)

    @app.post("/internal/v1/jobs/lease", dependencies=internal_auth)
    def lease(request: LeaseRequest):
        return service().lease_job(request)

    @app.post("/internal/v1/jobs/{job_id}/heartbeat", dependencies=internal_auth)
    def heartbeat(job_id: str, request: HeartbeatRequest):
        return service().heartbeat(job_id, request.worker_id, request.lease_token, request.lease_seconds)

    @app.post("/internal/v1/jobs/{job_id}/abandon", dependencies=internal_auth)
    def abandon(job_id: str, request: AbandonRequest):
        evidence = request.model_dump(by_alias=True, exclude={"lease_token"})
        return service().abandon(job_id, request.worker_id, request.lease_token, evidence)

    @app.post("/internal/v1/jobs/{job_id}/inspection-result", dependencies=internal_auth)
    def inspection_result(job_id: str, request: InspectionResult):
        return service().inspection_result(job_id, request.worker_id, request.lease_token, request.status, request.reason,
                                           {**request.evidence, "questionIds": request.question_ids})

    @app.post("/internal/v1/operations/{operation_id}/transition", dependencies=internal_auth)
    def transition(operation_id: str, request: OperationTransition):
        return service().transition(operation_id, request)

    @app.post("/internal/v1/operations/{operation_id}/receipt", dependencies=internal_auth)
    def receipt(operation_id: str, request: ReceiptRecord):
        result = service().record_receipt(operation_id, request)
        if getattr(app.state, "mail_service", None):
            try:
                app.state.mail_service.on_receipt_verified(result["case"]["id"], result["operation"], result["receipt"])
            except Exception as exc:
                LOGGER.warning("Mail receipt hook pending reconciliation (%s)", type(exc).__name__)
        return result

    @app.post("/internal/v1/operations/{operation_id}/fault", dependencies=internal_auth)
    def fault(operation_id: str, request: FaultRequest):
        return service().arm_fault(operation_id, request.armed)

    @app.post("/internal/v1/cases/{case_id}/events", dependencies=internal_auth)
    def event(case_id: str, request: CaseEventInput):
        return service().add_event(case_id, request)

    @app.get("/internal/v1/cases/{case_id}/evidence", dependencies=internal_auth)
    def evidence(case_id: str):
        return service().presenter_evidence(case_id)

    @app.post("/internal/v1/cases/{case_id}/follow-up-request", dependencies=internal_auth)
    def follow_up_request(case_id: str, request: FollowUpRequest):
        return service().request_follow_up(case_id, request)

    @app.post("/internal/v1/cases/{case_id}/follow-up-inspection", dependencies=internal_auth)
    def follow_up_inspection(case_id: str, request: FollowUpInspectionRequest):
        return service().request_follow_up_inspection(case_id, request)

    @app.post("/internal/v1/research/import", dependencies=internal_auth)
    def import_research(request: ResearchBatch):
        service()
        try:
            return app.state.research_importer.import_batch(request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/internal/v1/research/imports/{batch_id}", dependencies=internal_auth)
    def import_status(batch_id: str):
        service()
        item = app.state.db.import_runs.find_one({"id": batch_id})
        if not item:
            raise HTTPException(404, "Import run not found")
        return document(item)

    @app.post("/internal/v1/artifacts", dependencies=internal_auth)
    def upload_artifact(request: ArtifactUpload):
        service()
        try:
            return app.state.artifact_store.put(request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/internal/v1/artifacts/{artifact_id}", dependencies=internal_auth)
    def artifact_metadata(artifact_id: str):
        service()
        item = app.state.artifact_store.get_metadata(artifact_id)
        if not item:
            raise HTTPException(404, "Artifact not found")
        return item

    @app.get("/internal/v1/artifacts/{artifact_id}/content", dependencies=internal_auth)
    def artifact_content(artifact_id: str):
        service()
        item = app.state.artifact_store.get_metadata(artifact_id)
        if not item or item["status"] != "ready":
            raise HTTPException(404, "Ready artifact not found")
        return Response(app.state.artifact_store.read(artifact_id), media_type=item["mimeType"], headers={"X-Content-SHA256": item["sha256"]})

    @app.post("/internal/v1/retrieval/procedures", dependencies=internal_auth)
    def retrieve_procedures(request: RetrievalRequest):
        service()
        try:
            from .retrieval import retrieve_procedures
        except ImportError:
            return {"status": "assistance_required", "candidates": [], "evidence": {"reason": "Native retrieval module not installed"}}
        return retrieve_procedures(app.state.db, request.query, request.authority_id, request.issue_id, category_id=request.category_id, limit=request.limit)

    @app.post("/internal/v1/retrieval/lessons", dependencies=internal_auth)
    def retrieve_lessons(request: LessonRetrievalRequest):
        service()
        try:
            from .retrieval import retrieve_lessons
        except ImportError:
            return {"status": "assistance_required", "candidates": [], "evidence": {"reason": "Native retrieval module not installed"}}
        return retrieve_lessons(app.state.db, request.query, request.authority_id, request.issue_id,
                               category_id=request.category_id, limit=request.limit, portal_id=request.portal_id,
                               form_family=request.form_family, form_version=request.form_version,
                               workflow_kind=request.workflow_kind, withhold_lesson_ids=request.withhold_lesson_ids)

    @app.post("/internal/v1/retrieval/lessons/promote", dependencies=internal_auth)
    def promote_lesson(request: dict[str, Any]):
        service()
        try:
            from .retrieval import ProceduralLesson, promote_lesson
            model = ProceduralLesson.model_validate(request)
            return document(promote_lesson(app.state.db, model))
        except ImportError as exc:
            raise HTTPException(503, "Native lesson promotion is not available") from exc
        except ValidationError as exc:
            raise HTTPException(422, "Lesson does not match the verified memory contract") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/internal/v1/retrieval/verify-record", dependencies=internal_auth)
    def verify_record(request: VerifyRecordRequest):
        service()
        try:
            from .retrieval import verify_record_search
        except ImportError as exc:
            raise HTTPException(503, "Native record verification is not available") from exc
        if request.expected_source_version:
            record = app.state.db[request.collection].find_one({"id": request.id})
            if not record or record.get("sourceVersion") != request.expected_source_version:
                raise HTTPException(409, "Record version changed before verification")
        return verify_record_search(app.state.db, request.collection, request.id)

    try:
        from .mail import build_router
    except ImportError:
        pass
    else:
        # Build against a lazy proxy because mail service initialization needs the live DB.
        class MailProxy:
            def __getattr__(self, name: str):
                target = getattr(app.state, "mail_service", None)
                if target is None:
                    raise HTTPException(503, "Mail transport is not ready")
                return getattr(target, name)
        app.include_router(build_router(MailProxy()), dependencies=internal_auth)
    return app


def _preview(settings: Settings, request: RoutePreview) -> dict:
    # This method performs no database reads or writes.
    pure = object.__new__(CaseService)
    pure.settings = settings
    return pure.route_preview(request.issue_id, request.location, request.answers)


app = create_app()
