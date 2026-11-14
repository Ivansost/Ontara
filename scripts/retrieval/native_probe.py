#!/usr/bin/env python3
"""Reproduce the small, labelled native index/text/update proof in Atlas.

No embedding key, embedding API client, supplied vector or internal mutation is
used. Run from repository root with the API dependencies installed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import monotonic, sleep
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.retrieval.indexes import INDEX_NAMES, MODEL, ensure_native_indexes, inspect_native_index
from app.retrieval.service import build_text_pipeline

TEXT_V1 = "Synthetic native-index diagnostic only. A blue inspection flag at the test bridge marks a pothole observation. Record the road name and travel direction for a controlled receiving portal."
TEXT_V2 = "Synthetic native-index diagnostic only. The follow-up page split location into road or intersection, direction and position, and added a required nearest landmark. Ask the resident for the missing landmark, obtain approval, update the existing ticket, and verify its acknowledgement."
AUTHORITY = "__native_diagnostic_only__"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def scope(version: str) -> dict:
    return {"authorityId": AUTHORITY, "issueIds": "roads-pothole", "categoryId": "roads", "visibility": "public", "current": True, "verificationStatus": "partial", "sourceVersion": version}


def search(db: Any, collection: str, query: str, version: str) -> dict:
    pipeline = build_text_pipeline(collection, query, scope(version), limit=3)
    records = list(db[collection].aggregate(pipeline, maxTimeMS=15000))
    return {"at": timestamp(), "pipeline": pipeline, "records": records}


def wait_for(db: Any, collection: str, record_id: str, version: str, query: str, timeout: int) -> dict:
    deadline = monotonic() + timeout
    attempts = 0
    while monotonic() < deadline:
        state = inspect_native_index(db, collection)
        if state["status"] != "MISSING" and not state["configurationMatches"]:
            return {"status": "assistance_required", "reason": "Native index configuration mismatch", "index": state, "attempts": attempts}
        if state["status"] in {"FAILED", "STALE"}:
            return {"status": "assistance_required", "index": state, "attempts": attempts}
        if state["queryable"] and state["status"] == "READY":
            attempts += 1
            result = search(db, collection, query, version)
            if any(r.get("id") == record_id and r.get("sourceVersion") == version for r in result["records"]):
                return {"status": "ready", "index": state, "attempts": attempts, **result}
        sleep(3)
    return {"status": "pending", "reason": "Native asynchronous processing did not finish within the bounded probe", "attempts": attempts}


def generated_summary(db: Any, collection: str, record_id: str) -> dict:
    """Documented read-only inspection. Never write the reserved namespace."""
    indexes = list(db[collection].list_search_indexes(name=INDEX_NAMES[collection]))
    index_id = indexes[0].get("id") if indexes else None
    if not index_id:
        return {"available": False, "readOnly": True}
    internal = db.client["__mdb_internal_search"]
    names = [n for n in internal.list_collection_names() if n.startswith(str(index_id) + "-")]
    if len(names) != 1:
        return {"available": False, "readOnly": True, "matchingCollections": len(names)}
    rows = list(internal[names[0]].aggregate([
        {"$match": {"_id": record_id}},
        {"$project": {"_id": 1, "sourceVersion": 1, "embeddingType": {"$type": "$_autoEmbed.retrievalText"}, "embeddingByteLength": {"$binarySize": "$_autoEmbed.retrievalText"}}},
    ]))
    return {"available": bool(rows), "readOnly": True, "records": rows}


def run_probe(db: Any, timeout: int) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = {"runId": run_id, "startedAt": timestamp(), "model": MODEL, "diagnosticOnly": True, "appSuppliedVectors": False, "appEmbeddingApiCalls": 0, "collections": {}}
    for collection in INDEX_NAMES:
        record_id = f"native-diagnostic-{collection}-{run_id}"
        version1, version2 = f"{run_id}-v1", f"{run_id}-v2"
        base = {"_id": record_id, "id": record_id, **scope(version1), "retrievalText": TEXT_V1, "knowledgeKind": "diagnostic", "title": "Synthetic native diagnostic, excluded from verified runtime retrieval", "sourceIds": ["diagnostic-not-official"], "searchStatus": "pending"}
        base["issueIds"] = ["roads-pothole"]
        documents = [base]
        for suffix, changed in [("other-authority", {"authorityId": "__other_diagnostic_authority__"}), ("stale", {"current": False}), ("unverified", {"verificationStatus": "unverified"}), ("private", {"visibility": "case"})]:
            documents.append({**base, **changed, "_id": record_id + "-" + suffix, "id": record_id + "-" + suffix, "retrievalText": TEXT_V2})
        db[collection].insert_many(documents)
        result = {"recordId": record_id, "insertedDiagnosticRecords": len(documents)}
        evidence["collections"][collection] = result
        result["v1"] = wait_for(db, collection, record_id, version1, TEXT_V1, timeout)
        if result["v1"]["status"] != "ready":
            continue
        result["v2BeforeUpdate"] = search(db, collection, TEXT_V2, version1)
        result["scopeExclusionsPassed"] = [row.get("id") for row in result["v1"]["records"]] == [record_id]
        updated = db[collection].update_one({"_id": record_id, "sourceVersion": version1, "knowledgeKind": "diagnostic"}, {"$set": {"retrievalText": TEXT_V2, "sourceVersion": version2}})
        result["controlledUpdate"] = {"at": timestamp(), "matched": updated.matched_count, "modified": updated.modified_count, "sourceVersion": version2, "retrievalText": TEXT_V2}
        result["v2AfterUpdate"] = wait_for(db, collection, record_id, version2, TEXT_V2, timeout)
        if result["v2AfterUpdate"]["status"] == "ready":
            result["oldVersionAfterUpdate"] = search(db, collection, TEXT_V1, version1)
            result["currentVersionOnlyPassed"] = not result["oldVersionAfterUpdate"]["records"] and [row.get("id") for row in result["v2AfterUpdate"]["records"]] == [record_id]
            try:
                result["generatedEmbeddingEvidence"] = generated_summary(db, collection, record_id)
            except PyMongoError as exc:
                result["generatedEmbeddingEvidence"] = {"available": False, "readOnly": True, "errorType": type(exc).__name__, "errorCode": getattr(exc, "code", None)}
    evidence["completedAt"] = timestamp()
    evidence["status"] = "ready" if all(r.get("v2AfterUpdate", {}).get("status") == "ready" and r.get("scopeExclusionsPassed") and r.get("currentVersionOnlyPassed") for r in evidence["collections"].values()) else "pending"
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config/ontara/mongodb.env")
    parser.add_argument("--database", default="ontara", choices=["ontara"])
    parser.add_argument("--ensure-indexes", action="store_true", help="Create only missing approved native indexes")
    parser.add_argument("--run-probe", action="store_true", help="Insert labelled diagnostics and demonstrate an automatic text/version update")
    parser.add_argument("--timeout", type=int, default=120, choices=range(5, 301), metavar="5..300")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    env = dotenv_values(args.env_file) if args.env_file.exists() else {}
    uri = os.environ.get("MONGODB_URI") or env.get("MONGODB_URI")
    if not uri:
        print(json.dumps({"status": "assistance_required", "reason": "MONGODB_URI is missing"}))
        return 2
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000, tz_aware=True) as client:
            db = client[args.database]
            client.admin.command("ping")
            if args.ensure_indexes:
                ensure_native_indexes(db)
            if args.run_probe:
                result = run_probe(db, args.timeout)
            else:
                indexes = {name: inspect_native_index(db, name) for name in INDEX_NAMES}
                ready = all(item["status"] == "READY" and item["queryable"] and item["configurationMatches"] for item in indexes.values())
                failed = any(item["status"] in {"FAILED", "STALE", "DELETING"} or (item["status"] != "MISSING" and not item["configurationMatches"]) for item in indexes.values())
                result = {"status": "ready" if ready else "assistance_required" if failed else "pending", "indexes": indexes}
    except (PyMongoError, ValueError) as exc:
        result = {"status": "assistance_required", "errorType": type(exc).__name__, "errorCode": getattr(exc, "code", None)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status", "ready") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
