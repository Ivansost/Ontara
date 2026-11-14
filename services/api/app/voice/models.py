from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..models import Contract, IncidentLocation

CONSENT_VERSION = "2026-11-14.1"


class VoiceStart(Contract):
    request_id: str = Field(min_length=12, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    issue_id: str
    location: IncidentLocation
    answers: dict[str, str] = Field(default_factory=dict)
    voice_consent: Literal[True]
    consent_version: Literal["2026-11-14.1"]
    mode: Literal["voice", "text"] = "voice"


class VoiceAnswer(Contract):
    expected_revision: int = Field(ge=1)
    question_id: str = Field(min_length=1, max_length=100)
    value: str | None = Field(default=None, max_length=2000)


class VoiceBind(Contract):
    case_id: str = Field(min_length=1, max_length=100)
    case_version: int = Field(ge=1)
