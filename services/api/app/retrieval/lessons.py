"""Shareable lesson admission, kept separate from private case state."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ProceduralLesson(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    authority_id: str = Field(min_length=1, max_length=160)
    category_id: Literal["roads", "graffiti"]
    issue_ids: list[str] = Field(min_length=1, max_length=20)
    portal_id: Literal["roads", "graffiti"]
    workflow_kind: Literal["ticket_update"] = "ticket_update"
    form_family: str = Field(min_length=1, max_length=160)
    form_versions: list[str] = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=200)
    retrieval_text: str = Field(min_length=30, max_length=16000)
    problem: str = Field(min_length=1, max_length=2000)
    procedure: list[str] = Field(min_length=1, max_length=30)
    source_version: str = Field(min_length=1, max_length=100)
    evidence_refs: list[str] = Field(min_length=1, max_length=30)
    verification_status: Literal["verified"] = "verified"
    knowledge_kind: Literal["verified_rehearsal", "seeded_demo"] = "verified_rehearsal"
    verified_at: datetime
    valid_until: datetime | None = None
    visibility: Literal["public"] = "public"
    current: bool = True

    @model_validator(mode="after")
    def valid_dates(self) -> ProceduralLesson:
        if self.verified_at.tzinfo is None or (self.valid_until and self.valid_until.tzinfo is None):
            raise ValueError("Lesson verification/expiry dates must include a timezone")
        if self.valid_until and self.valid_until <= self.verified_at:
            raise ValueError("Lesson expiry must follow verification")
        shared_text = " ".join([self.title, self.retrieval_text, self.problem, *self.procedure])
        if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", shared_text, re.IGNORECASE):
            raise ValueError("Shared lesson text must exclude personal contact details")
        if re.search(r"(?:Bearer\s+\S+|mongodb(?:\+srv)?://|(?:api[_-]?key|access[_-]?token)\s*[:=]\s*\S+)", shared_text, re.IGNORECASE):
            raise ValueError("Shared lesson text must exclude credentials")
        return self


def promote_lesson(db: Any, lesson: ProceduralLesson | dict[str, Any]) -> dict[str, Any]:
    """Admit a lesson only with an actual verified update receipt in Atlas.

    The public lesson contains reference IDs and procedure semantics. Receipt
    bodies and private case facts remain in their original case collections.
    The authenticated backend is responsible for supplying redacted text.
    """
    lesson = lesson if isinstance(lesson, ProceduralLesson) else ProceduralLesson.model_validate(lesson)
    now = datetime.now(timezone.utc)
    if lesson.verified_at > now or (lesson.valid_until and lesson.valid_until <= now):
        raise ValueError("Lesson verification/validity is not current")
    verified_refs: list[str] = []
    for reference in lesson.evidence_refs:
        operation = db["operations"].find_one({"id": reference})
        if operation is None:
            operation = db["operations"].find_one({"_id": reference})
        if not operation or operation.get("state") != "receipt_verified":
            continue
        receipt = operation.get("receipt") or {}
        if (receipt.get("action") == "update" and receipt.get("portalId") == lesson.portal_id
                and operation.get("action") == "update" and operation.get("portalId") == lesson.portal_id
                and (operation.get("route") or {}).get("authorityId") == lesson.authority_id
                and (operation.get("payload") or {}).get("issueId") in lesson.issue_ids
                and str(receipt.get("formVersion")) in lesson.form_versions
                and receipt.get("receiptId") and receipt.get("ticketId")):
            verified_refs.append(reference)
    if not verified_refs:
        raise ValueError("Lesson promotion requires a receipt_verified update operation matching authority, issue, portal and form version")
    document = lesson.model_dump(by_alias=True, mode="python")
    content_hash = sha256(json.dumps(lesson.model_dump(by_alias=True, mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    document.update({
        "_id": lesson.id,
        "searchStatus": "pending",
        "retrievalTextHash": sha256(lesson.retrieval_text.encode()).hexdigest(),
        "nativeIndexName": "procedural_lessons_autoembed_v1",
        "embeddingModel": "voyage-4-large",
        "lessonContentHash": content_hash,
        "updatedAt": now,
    })
    existing = db["procedural_lessons"].find_one({"_id": lesson.id})
    if existing and existing.get("sourceVersion") == lesson.source_version:
        if existing.get("lessonContentHash") != content_hash:
            raise ValueError("Changed lesson content or scope requires a new sourceVersion")
        return {"id": lesson.id, "sourceVersion": lesson.source_version, "searchStatus": existing.get("searchStatus", "pending"), "unchanged": True}
    historical = db["procedural_lesson_versions"].find_one({"lessonId": lesson.id, "sourceVersion": lesson.source_version})
    if historical and historical.get("lessonContentHash") != content_hash:
        raise ValueError("An immutable lesson sourceVersion cannot be reused with changed content")
    if existing:
        previous_verification = existing.get("verifiedAt")
        if isinstance(previous_verification, datetime):
            previous_verification = previous_verification.replace(tzinfo=timezone.utc) if previous_verification.tzinfo is None else previous_verification
            if lesson.verified_at <= previous_verification:
                raise ValueError("A new current lesson version requires a newer verification")
    version_id = f"{lesson.id}:{lesson.source_version}"
    version_document = {**document, "_id": version_id, "id": version_id, "lessonId": lesson.id}
    db["procedural_lesson_versions"].update_one(
        {"lessonId": lesson.id, "sourceVersion": lesson.source_version},
        {"$setOnInsert": version_document}, upsert=True,
    )
    guard = {"_id": lesson.id, "sourceVersion": existing["sourceVersion"]} if existing else {"_id": lesson.id, "sourceVersion": {"$exists": False}}
    result = db["procedural_lessons"].replace_one(guard, document, upsert=existing is None)
    if existing and result.matched_count != 1:
        raise ValueError("Lesson changed during promotion; reload the current version")
    return {"id": lesson.id, "sourceVersion": lesson.source_version, "searchStatus": "pending", "unchanged": False}
