from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class IncidentLocation(Contract):
    municipality_id: str = Field(min_length=1, max_length=120)
    upper_tier_id: str | None = None
    incident_address: str = Field(min_length=3, max_length=500)
    fixture_id: str | None = None
    confirmed: bool = False
    reporter_municipality_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class Reporter(Contract):
    name: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=254)
    contact_consent: bool = False

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value and ("@" not in value or any(c.isspace() for c in value)):
            raise ValueError("Enter a valid email address")
        return value


class RoutePreview(Contract):
    issue_id: str
    location: IncidentLocation
    answers: dict[str, Any] = Field(default_factory=dict)


class CaseCreate(RoutePreview):
    reporter: Reporter | None = None


class CasePatch(Contract):
    expected_version: int = Field(ge=1)
    location: IncidentLocation | None = None
    answers: dict[str, Any] | None = None
    reporter: Reporter | None = None


class ApprovalRequest(Contract):
    version: int = Field(ge=1)


class FollowUpAnswer(Contract):
    expected_version: int = Field(ge=1)
    answers: dict[str, Any]


class Cancellation(Contract):
    reason: str | None = Field(default=None, max_length=500)


class LeaseRequest(Contract):
    worker_id: str = Field(min_length=1, max_length=150)
    lease_seconds: int = Field(default=90, ge=15, le=300)
    job_id: str | None = None
    case_id: str | None = None


class LeaseGuard(Contract):
    worker_id: str
    lease_token: str


class HeartbeatRequest(LeaseGuard):
    lease_seconds: int = Field(default=90, ge=15, le=300)


class OperationTransition(LeaseGuard):
    job_id: str
    expected_state: str
    state: Literal["prepared", "dispatch_started", "outcome_unknown", "reconciling", "receipt_verified", "needs_assistance", "stopped"]
    run_id: str | None = None
    attempt_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class Receipt(Contract):
    ticket_id: str
    receipt_id: str
    run_id: str
    portal_id: Literal["roads", "graffiti"]
    client_reference: str
    payload_digest: str
    action: Literal["create", "update"]
    accepted_at: datetime
    receipt_url: str
    ticket_url: str
    artifact_id: str | None = None
    update_url: str | None = None
    form_payload_digest: str | None = None
    form_version: int | None = None
    receipt_signature: str | None = None


class ReceiptRecord(LeaseGuard):
    job_id: str
    receipt: Receipt
    run_id: str | None = None
    attempt_id: str | None = None


class CaseEventInput(Contract):
    kind: str = Field(min_length=1, max_length=100)
    message: str = Field(max_length=2000)
    operation_id: str | None = None
    run_id: str | None = None
    attempt_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    visibility: Literal["resident", "presenter"] = "resident"


class FollowUpRequest(Contract):
    source_event_id: str
    question_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=2000)
    external_ticket_id: str | None = None
    operation_id: str | None = None


class Municipality(Contract):
    id: str
    name: str
    type: Literal["upper-tier", "lower-tier", "single-tier"]
    parent_id: str | None = None
    member_ids: list[str] = Field(default_factory=list)
    official_url: str
    population: int | None = Field(default=None, ge=0)
    population_year: int | None = None
    population_source_ids: list[str] = Field(default_factory=list)
    selection_rank: int | None = Field(default=None, ge=1)
    source_ids: list[str] = Field(default_factory=list)
    source_version: str = "1"
    boundary: dict[str, Any] | None = None


class SourceReference(Contract):
    id: str
    authority_id: str
    url: str
    title: str
    retrieved_at: datetime
    verified_at: datetime | None = None
    extracted_text: str = ""
    content_hash: str | None = None
    source_version: str = "1"
    artifact_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verification_status: Literal["verified", "partial", "unavailable"] = "verified"


class FormField(Contract):
    id: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class FormSnapshot(Contract):
    id: str
    authority_id: str
    procedure_id: str
    url: str
    observed_at: datetime
    source_version: str
    fields: list[FormField] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ServiceProcedure(Contract):
    id: str
    authority_id: str
    title: str
    category_id: Literal["roads", "graffiti"] = "roads"
    issue_ids: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    source_version: str
    retrieval_text: str = Field(min_length=20)
    responsibility_rules: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    follow_up_instructions: list[str] = Field(default_factory=list)
    official_form_url: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    form_snapshot_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    visibility: Literal["public"] = "public"
    verification_status: Literal["verified", "partial"] = "verified"
    current: bool = True
    research_status: Literal["verified", "partial"] = "verified"
    search_status: Literal["pending", "ready", "failed"] = "pending"
    integration_status: Literal["research_only", "demo_tested"] = "research_only"
    verified_at: datetime
    valid_until: datetime | None = None


class ArtifactUpload(Contract):
    id: str
    filename: str
    mime_type: str
    content_base64: str
    visibility: Literal["public", "case"]
    case_id: str | None = None
    source_id: str | None = None
    source_version: str
    authority_id: str | None = None
    operation_id: str | None = None
    run_id: str | None = None
    expected_sha256: str | None = None

    @model_validator(mode="after")
    def require_owner(self) -> ArtifactUpload:
        if self.visibility == "case" and not self.case_id:
            raise ValueError("Private artifacts require caseId")
        if self.visibility == "public" and not self.source_id:
            raise ValueError("Public artifacts require sourceId")
        return self


class ResearchBatch(Contract):
    schema_version: Literal["1.0"] = "1.0"
    batch_id: str
    municipalities: list[Municipality] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    procedures: list[ServiceProcedure] = Field(default_factory=list)
    form_snapshots: list[FormSnapshot] = Field(default_factory=list)
    artifacts: list[ArtifactUpload] = Field(default_factory=list)
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def roads_research_only(self) -> ResearchBatch:
        if any(p.category_id != "roads" for p in self.procedures):
            raise ValueError("The municipal research importer accepts Roads knowledge only")
        return self


class VisibilityCondition(Contract):
    question_id: str
    equals: Any


class QuestionOption(Contract):
    value: str
    label: str


class Question(Contract):
    id: str
    type: Literal["select", "text", "textarea", "date"]
    label: str
    required: bool
    description: str = ""
    options: list[QuestionOption] = Field(default_factory=list)
    min_length: int | None = None
    max_length: int | None = None
    visible_when: VisibilityCondition | None = None


class Questionnaire(Contract):
    issue_id: str
    version: str
    questions: list[Question]


class CatalogueNode(Contract):
    id: str
    slug: str
    label: str
    description: str
    kind: Literal["category", "group", "issue"]
    available: bool
    disabled_reason: str | None = None
    question_schema_id: str | None = None
    children: list[CatalogueNode] = Field(default_factory=list)


class CatalogueView(Contract):
    version: str
    categories: list[CatalogueNode]
    demo_locations: list[dict[str, Any]]
    disclaimer: str


class RouteDecision(Contract):
    supported: bool
    reason: str
    route: dict[str, Any] | None = None
    missing_answers: list[str] = Field(default_factory=list)
    urgent_handoff: bool = False
    demo: bool = True


class CaseView(Contract):
    id: str
    version: int
    issue_id: str
    location: IncidentLocation
    answers: dict[str, Any]
    reporter: Reporter | None = None
    stage: str
    route: dict[str, Any]
    pending_questions: list[Question] = Field(default_factory=list)
    approved_version: int | None = None
    current_operation_id: str | None = None
    receipt: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None
    run_id: str


class TimelineView(Contract):
    events: list[dict[str, Any]]


class Coordinates(Contract):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
