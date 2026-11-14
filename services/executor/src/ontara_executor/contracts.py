from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class BrowserContext(Contract):
    operation_id: str = Field(min_length=1, max_length=200)
    case_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    portal_id: Literal["roads", "graffiti"]
    client_reference: str = Field(min_length=1, max_length=200)
    payload_digest: str = Field(min_length=1, max_length=200)
    action: Literal["create", "update"]
    ticket_id: str | None = None
    update_url: str | None = None


class InspectRequest(BrowserContext):
    pass


class SubmitRequest(BrowserContext):
    form_fingerprint: str = Field(min_length=64, max_length=64)
    values: dict[str, str] = Field(max_length=40)
    return_receipt: bool = True


class FieldObservation(Contract):
    name: str
    label: str
    type: str
    required: bool = False
    disabled: bool = False
    options: list[str] = Field(default_factory=list)


class FormObservation(Contract):
    url: str
    action_url: str
    method: str
    form_version: str
    fingerprint: str
    fields: list[FieldObservation]
    observed_at: str


class BrowserResult(Contract):
    status: Literal["observed", "accepted", "not_found", "rejected", "unknown"]
    accepted: bool = False
    observation: FormObservation | None = None
    receipt: dict[str, Any] | None = None
    response_status: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
