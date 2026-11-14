from __future__ import annotations

import base64
import hashlib

import pytest

from app.models import ArtifactUpload, ResearchBatch
from app.research import ResearchImporter
from app.storage import now, redact


def artifact(id="source-artifact", content=b"actual obtained source bytes", **overrides):
    data = {"id": id, "filename": "source.html", "mimeType": "text/html", "contentBase64": base64.b64encode(content).decode(),
            "visibility": "public", "sourceId": "source-1", "sourceVersion": "1", "expectedSha256": hashlib.sha256(content).hexdigest()}
    data.update(overrides)
    return ArtifactUpload.model_validate(data)


def batch(**overrides):
    stamp = now().isoformat()
    value = {"batchId": "batch-1", "sources": [{"id": "source-1", "authorityId": "halton-region", "url": "https://official.example/roads",
        "title": "Official road procedure", "retrievedAt": stamp, "extractedText": "Regional road issues can be reported using this published contact.", "sourceVersion": "1"}],
        "procedures": [{"id": "procedure-1", "authorityId": "halton-region", "title": "Regional road issues", "issueIds": ["roads-pothole"],
        "sourceIds": ["source-1"], "sourceVersion": "1", "retrievalText": "Official published instructions for reporting regional road potholes.", "verifiedAt": stamp}]}
    value.update(overrides)
    return ResearchBatch.model_validate(value)


def test_gridfs_roundtrip_hash_and_same_id_replay(artifacts, store):
    upload = artifact()
    stored = artifacts.put(upload)
    assert stored["status"] == "ready" and artifacts.read(upload.id) == b"actual obtained source bytes"
    assert artifacts.put(upload)["gridfsFileId"] == stored["gridfsFileId"]
    assert store.db.ontara_files.files.count_documents({}) == 1
    with pytest.raises(ValueError):
        artifacts.put(artifact(content=b"changed content"))


def test_bad_hash_never_claims_ready(artifacts, store):
    with pytest.raises(ValueError):
        artifacts.put(artifact(expectedSha256="bad-hash"))
    assert store.db.artifacts.count_documents({"status": "ready"}) == 0


def test_private_artifact_cannot_be_reused_as_public(artifacts):
    upload = artifact(visibility="case", sourceId=None, caseId="case-private")
    artifacts.put(upload)
    with pytest.raises(ValueError):
        artifacts.put(artifact())


def test_batch_replay_is_idempotent_and_version_content_is_immutable(store, artifacts):
    importer = ResearchImporter(store, artifacts)
    first = batch()
    importer.import_batch(first)
    assert importer.import_batch(first)["replayed"] is True
    assert store.db.source_reference_versions.count_documents({}) == 1
    assert store.db.service_procedure_versions.count_documents({}) == 1
    changed = first.model_copy(deep=True)
    changed.batch_id = "batch-changed"
    changed.procedures[0].retrieval_text = "A materially different official road procedure with changed routing."
    with pytest.raises(ValueError):
        importer.import_batch(changed)
    assert store.db.import_runs.find_one({"id": "batch-changed"})["status"] == "failed"


def test_updated_version_invalidates_search_proof_and_keeps_old_source(store, artifacts):
    importer = ResearchImporter(store, artifacts)
    first = batch()
    importer.import_batch(first)
    store.db.service_procedures.update_one({"id": "procedure-1"}, {"$set": {"searchStatus": "ready", "searchVerification": {"version": "1"}}})
    updated = first.model_copy(deep=True)
    updated.batch_id = "batch-2"
    updated.procedures[0].source_version = "2"
    updated.procedures[0].retrieval_text = "Updated official regional road instructions with new published contact procedure."
    importer.import_batch(updated)
    record = store.db.service_procedures.find_one({"id": "procedure-1"})
    assert record["searchStatus"] == "pending" and "searchVerification" not in record
    assert store.db.service_procedure_versions.count_documents({}) == 2


def test_provenance_requires_known_sources_and_roads_scope(store, artifacts):
    importer = ResearchImporter(store, artifacts)
    invalid = batch()
    invalid.procedures[0].source_ids = ["missing-source"]
    with pytest.raises(ValueError):
        importer.import_batch(invalid)
    invalid = batch()
    invalid.procedures[0].issue_ids = ["graffiti-wall"]
    with pytest.raises(ValueError):
        importer.import_batch(invalid)


def test_execution_events_redact_credentials():
    result = redact({"Authorization": "Bearer secret", "nested": {"password": "secret"}, "message": "mongodb+srv://user:pass@cluster.example/db"})
    assert result["Authorization"] == "[redacted]" and result["nested"]["password"] == "[redacted]"
    assert "user:pass" not in result["message"]
