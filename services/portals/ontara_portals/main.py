from contextlib import asynccontextmanager
import hashlib
import hmac
from html import escape
import json
from pathlib import Path
import secrets
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from .config import Settings
from .forms import PORTALS, canonical_digest, form_schema, validate_values
from .html import form_html, lookup_html, page, receipt_html, ticket_html
from .store import Conflict, MongoStore, NotFound, now


StableId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Lookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runId: StableId
    clientReference: StableId
    payloadDigest: Digest


class Submission(Lookup):
    formVersion: int = Field(ge=1, le=2)
    values: dict = Field(default_factory=dict)
    accessToken: str = Field(default="", max_length=256)


class RunControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runId: StableId
    label: str = Field(default="Synthetic demo run", min_length=1, max_length=120)


class VersionControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, le=2)
    expectedVersion: int = Field(ge=1, le=2)


class ResolutionControl(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    resolutionId: StableId
    expectedTicketVersion: int = Field(ge=1)
    status: Literal["resolved"] = "resolved"
    isDemo: StrictBool = True
    simulated: StrictBool = True
    physicalRepairVerified: StrictBool = False

    @model_validator(mode="after")
    def only_simulated_completion(self):
        if not self.isDemo or not self.simulated or self.physicalRepairVerified:
            raise ValueError("Only simulated demo resolution with physicalRepairVerified false is permitted")
        return self


def create_app(settings: Settings | None = None, store: MongoStore | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        actual_settings = settings or Settings.from_environment()
        client = None
        actual_store = store
        if actual_store is None:
            client = MongoClient(actual_settings.mongodb_uri, appname="ontara-independent-demo-portals", serverSelectionTimeoutMS=10000, connectTimeoutMS=10000, maxPoolSize=10, tz_aware=True)
            try:
                client.admin.command("ping")
                # Majority acknowledgement makes the committed ticket durable before responding.
                actual_store = MongoStore(client.get_database(actual_settings.database_name, write_concern=WriteConcern("majority")))
                actual_store.ensure_indexes()
            except PyMongoError:
                client.close()
                raise RuntimeError("Demo receiving database is unavailable; verify its private credentials and network access") from None
        else:
            actual_store.ensure_indexes()
        app.state.settings = actual_settings
        app.state.store = actual_store
        for portal_id in PORTALS:
            for action, version in (("create", 1), ("update", 1), ("update", 2)):
                if portal_id == "graffiti" and version == 2:
                    continue
                schema = form_schema(portal_id, action, version)
                actual_store.save_snapshot(schema, form_html(portal_id, action, version, {"runId": "snapshot-only", "clientReference": "snapshot-only", "payloadDigest": "0" * 64}, "SNAPSHOT" if action == "update" else None))
        yield
        if client:
            client.close()

    app = FastAPI(title="Ontara independent demo receiving portals", version="1.0.0", lifespan=lifespan, docs_url="/api-docs", redoc_url=None)

    @app.middleware("http")
    async def response_controls(request: Request, call_next):
        # Prevent receipt capabilities and synthetic contact data entering browser caches/referrers.
        size = request.headers.get("content-length", "0")
        try:
            too_large = int(size) > 32768
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse({"detail": "Request body exceeds 32 KiB"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/portals/"):
            return HTMLResponse(page("Demo portal request could not be accepted", f'<h1>Request could not be accepted</h1><p class="error">{escape(str(exc.detail))}</p><p>Check the current form or reconcile the saved operation before submitting again.</p><a href="/">Return to demo portals</a>'), status_code=exc.status_code, headers=exc.headers)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo submitted values or capability tokens in validation failures.
        return JSONResponse({"detail": [{"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]} for item in exc.errors()]}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError):
        return JSONResponse({"detail": "Receiving database is unavailable; reconcile before retrying an external write"}, status_code=503)

    def receiver() -> MongoStore:
        return app.state.store

    def portal_check(portal_id: str) -> None:
        if portal_id not in PORTALS:
            raise HTTPException(404, "Unknown demo portal")

    def admin(authorization: Annotated[str | None, Header()] = None) -> None:
        actual = app.state.settings.admin_token
        candidate = authorization or ""
        if not candidate.startswith("Bearer ") or not secrets.compare_digest(candidate[7:].encode(), actual.encode()):
            raise HTTPException(401, "Presenter bearer authentication required", headers={"WWW-Authenticate": "Bearer"})

    def validated_lookup(data: dict) -> Lookup:
        try:
            return Lookup.model_validate(data)
        except ValidationError:
            raise HTTPException(422, "A valid runId, clientReference and lowercase SHA-256 payloadDigest are required") from None

    def envelope_for_form(run_id: str | None, reference: str | None, digest: str | None, portal_id: str, action: str) -> dict:
        run_id = run_id or "manual-" + secrets.token_hex(8)
        reference = reference or "operation-" + secrets.token_hex(16)
        digest = digest or canonical_digest({"manualOperation": reference, "runId": run_id, "portalId": portal_id, "action": action})
        return validated_lookup({"runId": run_id, "clientReference": reference, "payloadDigest": digest}).model_dump()

    def receipt_factory(envelope: dict, action: str, form_digest: str):
        config = app.state.settings
        portal_id = envelope["portalId"]
        schema = form_schema(portal_id, action, envelope["formVersion"])

        def make(ticket_id: str, access_token: str) -> dict:
            core = {"schemaVersion": 1, "receiptId": "RCP-" + secrets.token_hex(12).upper(), "ticketId": ticket_id, "runId": envelope["runId"], "portalId": portal_id, "authorityId": PORTALS[portal_id]["authorityId"], "routeId": PORTALS[portal_id]["routeId"], "clientReference": envelope["clientReference"], "payloadDigest": envelope["payloadDigest"], "formPayloadDigest": form_digest, "action": action, "acceptedAt": now(), "formVersion": envelope["formVersion"], "formSnapshotDigest": schema["snapshotDigest"]}
            signature = hmac.new(config.receipt_secret.encode(), ("ontara-demo-receipt-v1:" + json.dumps(core, sort_keys=True, separators=(",", ":"))).encode(), hashlib.sha256).hexdigest()
            capability = urlencode({"runId": envelope["runId"], "accessToken": access_token})
            lookup = urlencode({key: envelope[key] for key in ("runId", "clientReference", "payloadDigest")})
            path = f"{config.public_base_url}/portals/{portal_id}/tickets/{ticket_id}"
            return {**core, "receiptSignature": signature, "receiptUrl": f"{config.public_base_url}/portals/{portal_id}/lookup?{lookup}", "ticketUrl": f"{path}?{capability}", "updateUrl": f"{path}/update?{capability}", "isDemo": True}

        return make

    def submit(portal_id: str, action: str, raw: dict, ticket_id: str | None = None) -> tuple[dict, bool]:
        portal_check(portal_id)
        # Validate identifying fields before recording a run-scoped request. No body data is logged.
        lookup = validated_lookup({key: raw.get(key) for key in ("runId", "clientReference", "payloadDigest")})
        db = receiver()
        request_id = db.begin_request(lookup.runId, portal_id, action, lookup.clientReference, lookup.payloadDigest)
        try:
            try:
                submission = Submission.model_validate(raw)
            except ValidationError:
                raise HTTPException(422, "Invalid submission envelope") from None
            envelope = {**submission.model_dump(exclude={"values", "accessToken"}), "portalId": portal_id}
            if action == "update":
                bound = db.ticket(submission.runId, portal_id, ticket_id, submission.accessToken)
                if "resolution" in bound:
                    existing = db.lookup(submission.runId, portal_id, submission.clientReference)
                    if existing is None:
                        raise Conflict("Ticket is resolved in the demo; new updates are not accepted")
                    try:
                        replay_values = validate_values(portal_id, action, submission.formVersion, submission.values)
                    except ValueError as exc:
                        raise HTTPException(422, str(exc)) from None
                    replay_digest = canonical_digest({"portalId": portal_id, "action": action, "formVersion": submission.formVersion, "values": replay_values})
                    _, receipt, _ = db.check_existing(existing, submission.payloadDigest, replay_digest, action, ticket_id)
                    db.finish_request(request_id, "deduplicated", receipt["receiptId"])
                    return receipt, True
            current = db.form_version(submission.runId, portal_id, action)
            if submission.formVersion != current:
                raise HTTPException(409, f"Form changed. Inspect the current form version {current} before continuing this unfinished action.")
            try:
                values = validate_values(portal_id, action, current, submission.values)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            form_digest = canonical_digest({"portalId": portal_id, "action": action, "formVersion": current, "values": values})
            factory = receipt_factory(envelope, action, form_digest)
            db.ensure_run(submission.runId)
            if action == "create":
                ticket, receipt, duplicate = db.create_ticket(envelope, values, form_digest, factory)
            else:
                ticket, receipt, duplicate = db.update_ticket(envelope, values, form_digest, ticket_id, submission.accessToken, factory)
            db.finish_request(request_id, "deduplicated" if duplicate else "accepted", receipt["receiptId"])
            return receipt, duplicate
        except (Conflict, NotFound) as exc:
            db.finish_request(request_id, "conflict" if isinstance(exc, Conflict) else "not_found")
            raise HTTPException(409 if isinstance(exc, Conflict) else 404, str(exc)) from None
        except HTTPException as exc:
            db.finish_request(request_id, f"rejected_{exc.status_code}")
            raise

    async def form_data(request: Request) -> dict:
        raw = await request.form(max_fields=24, max_files=0, max_part_size=8192)
        if any(len(raw.getlist(key)) != 1 for key in raw):
            raise HTTPException(422, "Each form field must occur once")
        metadata = {"runId", "clientReference", "payloadDigest", "formVersion", "accessToken"}
        result = {key: raw[key] for key in metadata if key in raw}
        result["values"] = {key: value for key, value in raw.items() if key not in metadata}
        return result

    def lookup_receipt(portal_id: str, run_id: str, reference: str, digest: str) -> dict:
        portal_check(portal_id)
        request_data = validated_lookup({"runId": run_id, "clientReference": reference, "payloadDigest": digest})
        db = receiver()
        request_id = db.begin_request(run_id, portal_id, "lookup", reference, digest)
        existing = db.lookup(run_id, portal_id, reference)
        if not existing:
            db.finish_request(request_id, "not_found")
            raise HTTPException(404, "No acceptance receipt found for this client reference")
        receipt = existing[1]
        if not secrets.compare_digest(receipt["payloadDigest"], request_data.payloadDigest):
            db.finish_request(request_id, "digest_mismatch")
            raise HTTPException(409, "Client reference exists with a different payload digest")
        db.finish_request(request_id, "matched", receipt["receiptId"])
        return receipt

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "ontara-portals", "persistence": "mongodb", "database": "ontara_demo", "isDemo": True}

    @app.get("/assets/portal.css", include_in_schema=False)
    def stylesheet():
        return Response(Path(__file__).with_name("portal.css").read_text(), media_type="text/css")

    @app.get("/", response_class=HTMLResponse)
    def home():
        links = "".join(f'<li><a href="/portals/{portal_id}/new">{escape(profile["title"])}</a><p>{escape(profile["description"])}</p></li>' for portal_id, profile in PORTALS.items())
        return page("Ontara demo receiving systems", '<h1>Municipal demo receiving systems</h1><p>These independent forms receive synthetic reports for the Ontara hackathon demonstration.</p><ul class="portals">' + links + "</ul>")

    @app.get("/portals/{portal_id}/new", response_class=HTMLResponse)
    def new_form(portal_id: str, runId: str | None = None, clientReference: str | None = None, payloadDigest: str | None = None):
        portal_check(portal_id)
        envelope = envelope_for_form(runId, clientReference, payloadDigest, portal_id, "create")
        return form_html(portal_id, "create", 1, envelope)

    @app.post("/portals/{portal_id}/tickets", response_class=HTMLResponse)
    def browser_create(portal_id: str, data: Annotated[dict, Depends(form_data)]):
        receipt, duplicate = submit(portal_id, "create", data)
        return HTMLResponse(receipt_html(receipt, duplicate), status_code=200 if duplicate else 201)

    @app.get("/portals/{portal_id}/lookup", response_class=HTMLResponse)
    def browser_lookup(portal_id: str, runId: str | None = None, clientReference: str | None = None, payloadDigest: str | None = None):
        portal_check(portal_id)
        if not any((runId, clientReference, payloadDigest)):
            return lookup_html(portal_id)
        receipt = lookup_receipt(portal_id, runId, clientReference, payloadDigest)
        return receipt_html(receipt)

    @app.get("/portals/{portal_id}/tickets/{ticket_id}", response_class=HTMLResponse)
    def browser_ticket(portal_id: str, ticket_id: str, runId: str, accessToken: str):
        portal_check(portal_id)
        try:
            ticket = receiver().ticket(runId, portal_id, ticket_id, accessToken)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from None
        return ticket_html(ticket, ticket["receipts"][-1]["updateUrl"])

    @app.get("/portals/{portal_id}/tickets/{ticket_id}/update", response_class=HTMLResponse)
    def update_form(portal_id: str, ticket_id: str, runId: str, accessToken: str, clientReference: str | None = None, payloadDigest: str | None = None):
        portal_check(portal_id)
        try:
            ticket = receiver().ticket(runId, portal_id, ticket_id, accessToken)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from None
        if "resolution" in ticket:
            raise HTTPException(409, "Ticket is resolved in the demo; new updates are not accepted")
        envelope = envelope_for_form(runId, clientReference, payloadDigest, portal_id, "update")
        version = receiver().form_version(runId, portal_id, "update")
        return form_html(portal_id, "update", version, envelope, ticket_id, accessToken, ticket["currentValues"] if version == 1 else None)

    @app.post("/portals/{portal_id}/tickets/{ticket_id}/update", response_class=HTMLResponse)
    def browser_update(portal_id: str, ticket_id: str, data: Annotated[dict, Depends(form_data)]):
        receipt, duplicate = submit(portal_id, "update", data, ticket_id)
        return HTMLResponse(receipt_html(receipt, duplicate), status_code=200 if duplicate else 201)

    @app.get("/v1/portals")
    def portal_directory():
        return {"portals": [{"portalId": key, **profile, "isDemo": True} for key, profile in PORTALS.items()]}

    @app.get("/v1/portals/{portal_id}/form")
    def api_form(portal_id: str, runId: StableId, action: str = "create"):
        portal_check(portal_id)
        if action not in {"create", "update"}:
            raise HTTPException(422, "action must be create or update")
        return form_schema(portal_id, action, receiver().form_version(runId, portal_id, action))

    @app.post("/v1/portals/{portal_id}/tickets")
    def api_create(portal_id: str, data: Annotated[dict, Body()]):
        receipt, duplicate = submit(portal_id, "create", data)
        return JSONResponse({**receipt, "deduplicated": duplicate}, status_code=200 if duplicate else 201)

    @app.get("/v1/portals/{portal_id}/lookup")
    def api_lookup(portal_id: str, runId: str, clientReference: str, payloadDigest: str):
        return lookup_receipt(portal_id, runId, clientReference, payloadDigest)

    @app.post("/v1/portals/{portal_id}/tickets/{ticket_id}/update")
    def api_update(portal_id: str, ticket_id: str, data: Annotated[dict, Body()]):
        receipt, duplicate = submit(portal_id, "update", data, ticket_id)
        return JSONResponse({**receipt, "deduplicated": duplicate}, status_code=200 if duplicate else 201)

    @app.get("/v1/portals/{portal_id}/tickets/{ticket_id}/status")
    def receiving_ticket_status(portal_id: str, ticket_id: str, runId: StableId, accessToken: str):
        portal_check(portal_id)
        if portal_id != "roads":
            raise HTTPException(422, "Simulated resolution is limited to the Roads demo")
        try:
            return receiver().ticket_status(runId, portal_id, ticket_id, accessToken)
        except (NotFound, Conflict) as exc:
            raise HTTPException(404 if isinstance(exc, NotFound) else 409, str(exc)) from None

    @app.post("/internal/v1/runs/{run_id}/portals/{portal_id}/tickets/{ticket_id}/resolution", dependencies=[Depends(admin)])
    def mark_demo_resolution(run_id: StableId, portal_id: str, ticket_id: str, control: ResolutionControl):
        portal_check(portal_id)
        if portal_id != "roads":
            raise HTTPException(422, "Simulated resolution is limited to the Roads demo")
        try:
            return receiver().resolve_ticket(run_id, portal_id, ticket_id, control.resolutionId, control.expectedTicketVersion)
        except (NotFound, Conflict) as exc:
            raise HTTPException(404 if isinstance(exc, NotFound) else 409, str(exc)) from None

    @app.post("/internal/v1/runs", dependencies=[Depends(admin)])
    def create_run(control: RunControl):
        return receiver().ensure_run(control.runId, control.label)

    @app.get("/internal/v1/runs/{run_id}/evidence", dependencies=[Depends(admin)])
    def presenter_evidence(run_id: StableId):
        try:
            return receiver().evidence(run_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from None

    @app.post("/internal/v1/runs/{run_id}/portals/{portal_id}/form-version", dependencies=[Depends(admin)])
    def mutate_form(run_id: StableId, portal_id: str, control: VersionControl):
        portal_check(portal_id)
        if portal_id != "roads":
            raise HTTPException(422, "Changed-form scenario is scoped to the Roads portal")
        try:
            return receiver().change_form_version(run_id, portal_id, control.version, control.expectedVersion)
        except (NotFound, Conflict) as exc:
            raise HTTPException(404 if isinstance(exc, NotFound) else 409, str(exc)) from None

    return app


app = create_app()
