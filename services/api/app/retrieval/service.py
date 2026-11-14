"""Scoped native query.text retrieval with a fail-closed execution boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic
from typing import Any

from pymongo.errors import PyMongoError

from .indexes import INDEX_NAMES, MODEL, TEXT_PATH, inspect_native_index

MAX_CANDIDATES = 3
MAX_QUERY_CHARS = 8000
MAX_SEARCH_RESULTS = 10
MAX_SCOPED_VERSIONS = 250
SAFE_FIELDS = (
    "id", "authorityId", "issueIds", "categoryId", "title", "retrievalText",
    "sourceVersion", "sourceIds", "responsibilityRules", "requiredFacts",
    "steps", "constraints", "followUpInstructions", "officialFormUrl",
    "contactEmail", "contactPhone", "formSnapshotIds", "artifactIds", "coverage",
    "gaps", "visibility", "current", "verificationStatus", "verifiedAt",
    "validUntil", "researchStatus", "searchStatus", "integrationStatus",
    "portalId", "workflowKind", "formFamily", "formVersions", "problem",
    "procedure", "evidenceRefs", "knowledgeKind", "searchVerification",
)


def text_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def build_text_pipeline(
    collection_name: str, query: str, filters: dict[str, Any], *, limit: int = MAX_SEARCH_RESULTS,
) -> list[dict[str, Any]]:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Text query must contain 1–{MAX_QUERY_CHARS} characters")
    if not 1 <= limit <= MAX_SEARCH_RESULTS:
        raise ValueError("Native result limit must be between 1 and 10")
    return [
        {"$vectorSearch": {
            "index": INDEX_NAMES[collection_name], "path": TEXT_PATH,
            "query": {"text": query.strip()}, "exact": True,
            "limit": limit, "filter": filters,
        }},
        {"$project": {"_id": 0, **{field: 1 for field in SAFE_FIELDS}, "score": {"$meta": "vectorSearchScore"}}},
    ]


def _scope(authority_id: str, issue_id: str, category_id: str) -> dict[str, Any]:
    if not authority_id or not issue_id or category_id not in {"roads", "graffiti"}:
        raise ValueError("Explicit authority, issue and active category scope are required")
    return {
        "authorityId": authority_id, "issueIds": issue_id, "categoryId": category_id,
        "visibility": "public", "current": True, "verificationStatus": "verified",
    }


def _safe_error(exc: Exception) -> dict[str, Any]:
    # Driver exception messages may include a credential-bearing URI or host.
    return {"errorType": type(exc).__name__, "errorCode": getattr(exc, "code", None)}


def _current_record(collection: Any, record_id: str) -> dict[str, Any] | None:
    return collection.find_one({"id": record_id}) or collection.find_one({"_id": record_id})


def _eligibility(
    document: dict[str, Any], filters: dict[str, Any], now: datetime,
    *, lesson: bool, require_proof: bool,
) -> str | None:
    for key, expected in filters.items():
        if key == "id" or isinstance(expected, dict):
            continue
        actual = document.get(key)
        if isinstance(actual, list):
            if expected not in actual:
                return f"scope_changed:{key}"
        elif actual != expected:
            return f"scope_changed:{key}"
    if document.get("validUntil") is not None:
        expiry = utc_datetime(document["validUntil"])
        if expiry is None or expiry <= now:
            return "expired_or_invalid_validity"
    verified = utc_datetime(document.get("verifiedAt"))
    if verified is None or verified > now:
        return "missing_or_invalid_verification_time"
    if not document.get("sourceVersion") or not document.get("retrievalText"):
        return "missing_version_or_text"
    if lesson:
        if document.get("knowledgeKind") not in {"verified_rehearsal", "seeded_demo"}:
            return "unverified_lesson_kind"
        if not document.get("evidenceRefs"):
            return "missing_outcome_evidence"
    elif not document.get("sourceIds"):
        return "missing_source_provenance"
    if require_proof:
        proof = document.get("searchVerification") or {}
        if (document.get("searchStatus") != "ready"
                or proof.get("sourceVersion") != document["sourceVersion"]
                or proof.get("retrievalTextHash") != text_hash(document["retrievalText"])
                or proof.get("indexName") != INDEX_NAMES["procedural_lessons" if lesson else "service_procedures"]
                or proof.get("nativeQuery") is not True):
            return "record_indexing_pending"
    return None


def _result(status: str, reason: str, evidence: dict[str, Any], candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "candidates": candidates or [], "evidence": evidence}


def _retrieve(
    db: Any, collection_name: str, query: str, filters: dict[str, Any], *,
    limit: int, withhold_lesson_ids: list[str] | None = None,
) -> dict[str, Any]:
    if not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError("At most three candidates may reach validation")
    pipeline = build_text_pipeline(collection_name, query, filters)
    started = monotonic()
    evidence: dict[str, Any] = {
        "collection": collection_name, "indexName": INDEX_NAMES[collection_name],
        "model": MODEL, "queryText": query.strip(), "nativeQuery": True,
        "queryExecuted": False, "pipeline": pipeline,
        "reranking": {"ran": False, "reason": "Optional reranking not enabled"},
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        state = inspect_native_index(db, collection_name)
        evidence["index"] = state
        if not state["configurationMatches"] and state["status"] != "MISSING":
            return _result("assistance_required", "Native index configuration does not match the approved model and scope", evidence)
        if state["status"] in {"FAILED", "STALE", "DELETING"}:
            return _result("assistance_required", "Native indexing is failed, stale or unavailable", evidence)
        if not state["queryable"] or state["status"] != "READY":
            return _result("pending", "Atlas is still preparing the native index", evidence)
        # Search normally looks up source documents after scoring. A lagging
        # search node could therefore score an older embedding but return a newer
        # source document. Bind every candidate to an exact live ID/version pair
        # inside the native prefilter as well as revalidating after retrieval.
        versions = list(db[collection_name].find(filters, {"_id": 0, "id": 1, "sourceVersion": 1}).limit(MAX_SCOPED_VERSIONS + 1))
        if len(versions) > MAX_SCOPED_VERSIONS:
            return _result("assistance_required", "The procedure scope is too broad; narrow the authority and issue", evidence)
        pairs = [{"id": record["id"], "sourceVersion": record["sourceVersion"]} for record in versions if record.get("id") and record.get("sourceVersion")]
        if not pairs:
            return _result("assistance_required", "No current verified knowledge exists in the requested scope", evidence)
        pipeline = build_text_pipeline(collection_name, query, {"$and": [filters, {"$or": pairs}]})
        evidence["pipeline"] = pipeline
        evidence["scopedVersions"] = pairs
        results = list(db[collection_name].aggregate(pipeline, maxTimeMS=15000))
        evidence["queryExecuted"] = True
        evidence["returnedIds"] = [d.get("id") for d in results]
        candidates: list[dict[str, Any]] = []
        rejected = []
        pending = False
        now = datetime.now(timezone.utc)
        withheld = set(withhold_lesson_ids or [])
        for result in results:
            record_id = result.get("id")
            if record_id in withheld:
                rejected.append({"id": record_id, "reason": "withheld_for_policy_comparison"})
                continue
            if not isinstance(record_id, str):
                rejected.append({"id": None, "reason": "missing_record_id"})
                continue
            current = _current_record(db[collection_name], record_id)
            if not current:
                rejected.append({"id": record_id, "reason": "record_removed"})
                continue
            reason = _eligibility(current, filters, now, lesson=collection_name == "procedural_lessons", require_proof=True)
            if not reason and (current.get("sourceVersion") != result.get("sourceVersion")
                               or current.get("retrievalText") != result.get("retrievalText")):
                reason = "record_changed_during_retrieval"
            if not reason and collection_name == "service_procedures":
                for source_id in current["sourceIds"]:
                    source = _current_record(db["source_references"], source_id)
                    if not source or source.get("authorityId") != filters["authorityId"] or source.get("verificationStatus") != "verified":
                        reason = "source_no_longer_verified"
                        break
            if reason:
                pending |= reason in {"record_indexing_pending", "record_changed_during_retrieval"}
                rejected.append({"id": record_id, "reason": reason})
                continue
            candidate = {field: current[field] for field in SAFE_FIELDS if field in current}
            candidate["score"] = result.get("score")
            candidate["verified"] = True
            candidates.append(candidate)
            if len(candidates) == limit:
                break
        evidence["rejected"] = rejected
        evidence["selectedIds"] = [d["id"] for d in candidates]
        evidence["elapsedMs"] = round((monotonic() - started) * 1000)
        if candidates:
            return _result("ready", "Eligible native search candidates require structured validation before execution", evidence, candidates)
        if pending:
            return _result("pending", "The current record version has not completed native search verification", evidence)
        return _result("assistance_required", "No applicable current verified knowledge was retrieved; execution must pause", evidence)
    except PyMongoError as exc:
        evidence.update(_safe_error(exc))
        evidence["elapsedMs"] = round((monotonic() - started) * 1000)
        return _result("assistance_required", "Atlas native retrieval is unavailable; execution must pause", evidence)


def retrieve_procedures(
    db: Any, query: str, authority_id: str, issue_id: str, *, category_id: str = "roads", limit: int = 3,
) -> dict[str, Any]:
    return _retrieve(db, "service_procedures", query, _scope(authority_id, issue_id, category_id), limit=limit)


def retrieve_lessons(
    db: Any, query: str, authority_id: str, issue_id: str, *, portal_id: str,
    form_family: str, form_version: str, workflow_kind: str = "ticket_update",
    category_id: str = "roads", limit: int = 3,
    withhold_lesson_ids: list[str] | None = None,
) -> dict[str, Any]:
    if portal_id not in {"roads", "graffiti"} or not form_family or not form_version or workflow_kind != "ticket_update":
        raise ValueError("Explicit allowed portal and form/workflow scope are required")
    filters = _scope(authority_id, issue_id, category_id)
    filters.update({"portalId": portal_id, "workflowKind": workflow_kind, "formFamily": form_family, "formVersions": form_version})
    return _retrieve(db, "procedural_lessons", query, filters, limit=limit, withhold_lesson_ids=withhold_lesson_ids)


def verify_record_search(
    db: Any, collection_name: str, record_id: str, *, expected_source_version: str | None = None,
) -> dict[str, Any]:
    """One bounded native text query proves a particular imported text/version.

    The version is pre-filtered by the search index, not merely read back from
    MongoDB after a query. Call again later for asynchronous pending records.
    """
    if collection_name not in INDEX_NAMES:
        raise ValueError("Only procedure and lesson records may be search-verified")
    collection = db[collection_name]
    record = _current_record(collection, record_id)
    if not record:
        return {"status": "assistance_required", "id": record_id, "reason": "Record not found"}
    if expected_source_version is not None and record.get("sourceVersion") != expected_source_version:
        return {"status": "assistance_required", "id": record_id, "reason": "Imported source version does not match the expected batch version", "expectedSourceVersion": expected_source_version, "currentSourceVersion": record.get("sourceVersion")}
    filters = _scope(record.get("authorityId"), (record.get("issueIds") or [None])[0], record.get("categoryId", "roads"))
    reason = _eligibility(record, filters, datetime.now(timezone.utc), lesson=collection_name == "procedural_lessons", require_proof=False)
    if reason:
        return {"status": "assistance_required", "id": record_id, "reason": reason}
    filters.update({"id": record_id, "sourceVersion": record["sourceVersion"]})
    query_text = record["retrievalText"][:MAX_QUERY_CHARS]
    pipeline = build_text_pipeline(collection_name, query_text, filters, limit=1)
    try:
        state = inspect_native_index(db, collection_name)
        if not state["queryable"] or state["status"] != "READY":
            return {"status": "pending" if state["status"] not in {"FAILED", "STALE"} else "assistance_required", "id": record_id, "index": state}
        if not state["configurationMatches"]:
            return {"status": "assistance_required", "id": record_id, "reason": "Index configuration mismatch", "index": state}
        results = list(collection.aggregate(pipeline, maxTimeMS=15000))
        matched = next((result for result in results if result.get("id") == record_id
                        and result.get("sourceVersion") == record["sourceVersion"]
                        and result.get("retrievalText") == record["retrievalText"]), None)
        if not matched:
            return {"status": "pending", "id": record_id, "reason": "Current text/version not yet searchable", "pipeline": pipeline}
        proof = {
            "nativeQuery": True, "model": MODEL, "indexName": INDEX_NAMES[collection_name],
            "sourceVersion": record["sourceVersion"], "retrievalTextHash": text_hash(record["retrievalText"]),
            "verifiedAt": datetime.now(timezone.utc), "queryText": query_text,
            "queryTruncated": len(record["retrievalText"]) > MAX_QUERY_CHARS,
            "pipeline": pipeline, "score": matched.get("score"),
        }
        outcome = collection.update_one(
            {"_id": record["_id"], "sourceVersion": record["sourceVersion"], "retrievalText": record["retrievalText"]},
            {"$set": {"searchStatus": "ready", "searchVerification": proof}},
        )
        if outcome.matched_count != 1:
            return {"status": "pending", "id": record_id, "reason": "Record changed during search verification"}
        return {"status": "ready", "id": record_id, "evidence": proof, "index": state}
    except PyMongoError as exc:
        return {"status": "assistance_required", "id": record_id, "reason": "Native search verification failed", **_safe_error(exc)}
