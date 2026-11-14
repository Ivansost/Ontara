from __future__ import annotations

import hashlib
import json
from typing import Any

from .catalogue import ROAD_ISSUES
from .models import ResearchBatch
from .storage import ArtifactStore, Store, document, now


def digest_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


class ResearchImporter:
    def __init__(self, store: Store, artifacts: ArtifactStore):
        self.store, self.db, self.artifacts = store, store.db, artifacts

    def import_batch(self, batch: ResearchBatch) -> dict:
        body = batch.model_dump(by_alias=True, mode="json")
        batch_hash = digest_json(body)
        previous = self.db.import_runs.find_one({"id": batch.batch_id})
        if previous and previous.get("contentHash") != batch_hash:
            raise ValueError("batchId is immutable; use a new batchId for changed content")
        if previous and previous.get("status") == "completed":
            return {**document(previous), "replayed": True}
        source_ids = {s.id for s in batch.sources}
        procedure_ids = {p.id for p in batch.procedures}
        if len(source_ids) != len(batch.sources) or len(procedure_ids) != len(batch.procedures):
            raise ValueError("Duplicate source or procedure IDs in batch")
        for procedure in batch.procedures:
            if not set(procedure.issue_ids).issubset(ROAD_ISSUES):
                raise ValueError(f"Unknown or non-Roads issue ID in {procedure.id}")
            for source_id in procedure.source_ids:
                if source_id not in source_ids and not self.db.source_references.find_one({"id": source_id}):
                    raise ValueError(f"Unknown source reference {source_id}")
        for snapshot in batch.form_snapshots:
            if snapshot.procedure_id not in procedure_ids and not self.db.service_procedures.find_one({"id": snapshot.procedure_id}):
                raise ValueError(f"Unknown procedure for form snapshot {snapshot.id}")
        run = {"id": batch.batch_id, "contentHash": batch_hash, "status": "started", "startedAt": now(),
               "municipalityIds": [m.id for m in batch.municipalities], "procedureIds": list(procedure_ids),
               "sourceIds": list(source_ids), "coverage": batch.coverage, "gaps": batch.gaps,
               "searchStatus": "pending", "schemaVersion": batch.schema_version}
        self.db.import_runs.update_one({"id": batch.batch_id}, {"$set": run}, upsert=True)
        counts = {"municipalities": 0, "sources": 0, "procedures": 0, "formSnapshots": 0, "artifacts": 0}
        try:
            for artifact in batch.artifacts:
                self.artifacts.put(artifact)
                counts["artifacts"] += 1
            for source in batch.sources:
                item = source.model_dump(by_alias=True)
                text_hash = hashlib.sha256(source.extracted_text.encode()).hexdigest()
                if source.content_hash and source.content_hash != text_hash:
                    raise ValueError(f"Source {source.id} contentHash must hash UTF-8 extractedText")
                item["contentHash"] = text_hash
                self._check_artifacts(item)
                self._versioned("source_references", "source_reference_versions", "sourceId", item)
                counts["sources"] += 1
            for municipality in batch.municipalities:
                item = municipality.model_dump(by_alias=True)
                self.db.municipalities.update_one({"id": item["id"]}, {"$set": {**item, "updatedAt": now()}}, upsert=True)
                counts["municipalities"] += 1
            for procedure in batch.procedures:
                item = procedure.model_dump(by_alias=True)
                self._check_artifacts(item)
                # Search readiness is established by native query probes, never the importer.
                item["searchStatus"] = "pending"
                self._versioned("service_procedures", "service_procedure_versions", "procedureId", item)
                counts["procedures"] += 1
            for snapshot in batch.form_snapshots:
                item = snapshot.model_dump(by_alias=True)
                self._check_artifacts(item)
                item["contentHash"] = digest_json(item)
                existing = self.db.form_snapshots.find_one({"id": item["id"]})
                if existing and existing.get("contentHash") != item["contentHash"]:
                    raise ValueError("Form snapshot IDs are immutable; use a new ID for a changed form")
                self.db.form_snapshots.update_one({"id": item["id"]}, {"$setOnInsert": item}, upsert=True)
                counts["formSnapshots"] += 1
            self.db.import_runs.update_one({"id": batch.batch_id}, {"$set": {"status": "completed", "completedAt": now(), "counts": counts}, "$unset": {"error": ""}})
        except Exception as exc:
            self.db.import_runs.update_one({"id": batch.batch_id}, {"$set": {"status": "failed", "error": str(exc), "counts": counts, "updatedAt": now()}})
            raise
        return document(self.db.import_runs.find_one({"id": batch.batch_id}))

    def _check_artifacts(self, item: dict) -> None:
        for artifact_id in item.get("artifactIds", []):
            artifact = self.artifacts.get_metadata(artifact_id)
            if not artifact or artifact["status"] != "ready" or artifact["visibility"] != "public":
                raise ValueError(f"Public ready artifact required: {artifact_id}")

    def _versioned(self, current_collection: str, versions_collection: str, owner_key: str, item: dict) -> None:
        # Preserve complete immutable source/procedure content used by approved actions.
        content_hash = digest_json({k: v for k, v in item.items() if k not in {"searchStatus", "current"}})
        version_id = f"{item['id']}:{item['sourceVersion']}"
        old_version = self.db[versions_collection].find_one({"id": version_id})
        if old_version and old_version.get("recordHash") != content_hash:
            raise ValueError(f"{owner_key} {item['id']} sourceVersion is immutable")
        self.db[versions_collection].update_one({"id": version_id}, {"$setOnInsert": {
            **item, "id": version_id, owner_key: item["id"], "recordHash": content_hash, "importedAt": now(),
        }}, upsert=True)
        current = self.db[current_collection].find_one({"id": item["id"]})
        incoming_time = item.get("verifiedAt") or item.get("retrievedAt")
        current_time = (current or {}).get("verifiedAt") or (current or {}).get("retrievedAt")
        if current_time and incoming_time and current_time > incoming_time:
            return
        if current and current.get("sourceVersion") == item["sourceVersion"]:
            # Do not reset a readiness probe merely because an unchanged source is reimported.
            item["searchStatus"] = current.get("searchStatus", item.get("searchStatus", "pending"))
        update = {"$set": {**item, "recordHash": content_hash, "updatedAt": now()}}
        if current and (current.get("sourceVersion") != item["sourceVersion"] or current.get("retrievalText") != item.get("retrievalText")):
            update["$unset"] = {"searchVerification": ""}
        self.db[current_collection].update_one({"id": item["id"]}, update, upsert=True)
