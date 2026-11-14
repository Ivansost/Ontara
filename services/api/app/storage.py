from __future__ import annotations

import base64
import hashlib
import io
import re
import uuid
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from bson import ObjectId
from gridfs import GridFSBucket
from pymongo import ASCENDING, MongoClient
from pymongo import ReturnDocument
from pymongo.database import Database

from .config import Settings
from .models import ArtifactUpload


def now() -> datetime:
    return datetime.now(timezone.utc)


def identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def document(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: document(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, (list, tuple)):
        return [document(v) for v in value]
    if isinstance(value, ObjectId):
        return str(value)
    return value


class Store:
    def __init__(self, db: Database, *, transactions: bool = True):
        self.db = db
        self.transactions = transactions

    @classmethod
    def connect(cls, settings: Settings) -> Store:
        if not settings.mongodb_uri:
            raise RuntimeError("MONGODB_URI is required")
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000, tz_aware=True)
        return cls(client[settings.database_name])

    @contextmanager
    def atomic(self) -> Iterator[dict]:
        if not self.transactions:
            yield {}
            return
        with self.db.client.start_session() as session:
            with session.start_transaction():
                yield {"session": session}

    def ensure_indexes(self) -> None:
        for name in ("cases", "case_versions", "operations", "jobs", "case_events", "execution_events",
                     "municipalities", "source_references", "source_reference_versions", "service_procedures",
                     "service_procedure_versions", "form_snapshots", "artifacts", "import_runs"):
            self.db[name].create_index("id", unique=True)
        self.db.cases.create_index([("ownerKey", ASCENDING), ("updatedAt", ASCENDING)])
        self.db.case_versions.create_index([("caseId", 1), ("version", 1)], unique=True)
        self.db.operations.create_index([("caseId", 1), ("caseVersion", 1), ("action", 1)], unique=True)
        self.db.operations.create_index([("state", 1), ("updatedAt", 1)])
        self.db.jobs.create_index("operationId")
        self.db.jobs.create_index([("state", 1), ("leaseUntil", 1), ("createdAt", 1)])
        self.db.case_events.create_index([("caseId", 1), ("createdAt", 1)])
        self.db.case_events.create_index("dedupeKey", unique=True, sparse=True)
        self.db.execution_events.create_index([("caseId", 1), ("createdAt", 1)])
        self.db.source_reference_versions.create_index([("sourceId", 1), ("sourceVersion", 1)], unique=True)
        self.db.service_procedure_versions.create_index([("procedureId", 1), ("sourceVersion", 1)], unique=True)
        self.db.artifacts.create_index([("visibility", 1), ("sourceId", 1), ("sourceVersion", 1), ("sha256", 1)])
        self.db.procedural_lessons.create_index("id", unique=True, sparse=True)
        self.db.procedural_lesson_versions.create_index("id", unique=True, sparse=True)
        self.db.procedural_lesson_versions.create_index([("lessonId", 1), ("sourceVersion", 1)], unique=True)


class ArtifactStore:
    """GridFS upload is separate from publishing ready metadata; retries reconcile."""

    def __init__(self, db: Database, max_bytes: int = 20 * 1024 * 1024):
        self.db = db
        self.bucket = GridFSBucket(db, bucket_name="ontara_files")
        self.max_bytes = max_bytes

    def put(self, upload: ArtifactUpload) -> dict:
        try:
            content = base64.b64decode(upload.content_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Artifact content must be valid base64") from exc
        if len(content) > self.max_bytes:
            raise ValueError("Artifact exceeds the configured upload limit")
        digest = hashlib.sha256(content).hexdigest()
        if upload.expected_sha256 and upload.expected_sha256 != digest:
            raise ValueError("Artifact SHA-256 does not match supplied content")
        owner = {"visibility": upload.visibility, "caseId": upload.case_id, "sourceId": upload.source_id,
                 "sourceVersion": upload.source_version}
        existing = self.db.artifacts.find_one({"id": upload.id})
        if existing:
            if any(existing.get(k) != v for k, v in owner.items()) or existing.get("sha256") != digest:
                raise ValueError("Artifact ID cannot be reused with different content or ownership")
            if existing.get("status") == "ready":
                # A metadata flag alone is not proof that the stored file still exists.
                self.bucket.open_download_stream(existing["gridfsFileId"]).close()
                return document(existing)
        metadata = {"id": upload.id, **owner, "filename": upload.filename, "mimeType": upload.mime_type,
                    "byteCount": len(content), "sha256": digest, "authorityId": upload.authority_id,
                    "operationId": upload.operation_id, "runId": upload.run_id, "status": "pending", "updatedAt": now()}
        self.db.artifacts.update_one({"id": upload.id}, {"$setOnInsert": {**metadata, "createdAt": now()}}, upsert=True)
        lease_token = secrets.token_urlsafe(24)
        locked = self.db.artifacts.find_one_and_update({"id": upload.id, "sha256": digest,
            "$or": [{"uploadLeaseUntil": {"$exists": False}}, {"uploadLeaseUntil": {"$lte": now()}}]},
            {"$set": {"status": "pending", "uploadLeaseToken": lease_token, "uploadLeaseUntil": now() + timedelta(minutes=5), "updatedAt": now()}},
            return_document=ReturnDocument.AFTER)
        if not locked:
            raise ValueError("An artifact upload is already in progress; reconcile before retrying")
        # A deterministic ID makes an interrupted finished upload discoverable on retry.
        file_id = f"{upload.id}:{digest}"
        try:
            if upload.visibility == "public":
                duplicate = self.db.ontara_files.files.find_one({"metadata.visibility": "public", "metadata.sha256": digest})
                if duplicate:
                    file_id = duplicate["_id"]
            file_record = self.db.ontara_files.files.find_one({"_id": file_id})
            if not file_record:
                # The upload lock permits cleanup of chunks from an interrupted upload.
                self.db.ontara_files.chunks.delete_many({"files_id": file_id})
                self.bucket.upload_from_stream_with_id(file_id, upload.filename, io.BytesIO(content), metadata={**owner, "sha256": digest, "mimeType": upload.mime_type})
            stored = self.bucket.open_download_stream(file_id).read()
            if hashlib.sha256(stored).hexdigest() != digest:
                raise ValueError("Stored artifact failed SHA-256 verification")
            self.db.artifacts.update_one({"id": upload.id, "sha256": digest, "uploadLeaseToken": lease_token}, {"$set": {"status": "ready", "gridfsFileId": file_id, "updatedAt": now()}, "$unset": {"error": "", "uploadLeaseToken": "", "uploadLeaseUntil": ""}})
        except Exception as exc:
            self.db.artifacts.update_one({"id": upload.id, "uploadLeaseToken": lease_token}, {"$set": {"status": "failed", "error": type(exc).__name__, "updatedAt": now()}, "$unset": {"uploadLeaseToken": "", "uploadLeaseUntil": ""}})
            raise
        return self.get_metadata(upload.id)

    def get_metadata(self, artifact_id: str) -> dict | None:
        item = self.db.artifacts.find_one({"id": artifact_id})
        return document(item) if item else None

    def read(self, artifact_id: str) -> bytes:
        item = self.db.artifacts.find_one({"id": artifact_id, "status": "ready"})
        if not item:
            raise KeyError("Ready artifact not found")
        content = self.bucket.open_download_stream(item["gridfsFileId"]).read()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Stored artifact failed SHA-256 verification")
        return content


SENSITIVE_KEYS = re.compile(r"authorization|cookie|password|secret|api.?key|access.?token|refresh.?token|lease.?token|fault.?token|update.?url|receipt.?signature|mongodb.?uri|chain.?of.?thought", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[redacted]" if SENSITIVE_KEYS.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"mongodb(?:\+srv)?://[^\s]+", "[redacted MongoDB URI]", value)
        value = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+", r"\1[redacted]", value)
        return re.sub(r"(?i)([?&](?:token|key|api_key|sig|signature|secret)=)[^&\s]+", r"\1[redacted]", value)
    return value
