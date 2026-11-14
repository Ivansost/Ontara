"""Explicit native Automated Embedding configuration; no model API client."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pymongo.operations import SearchIndexModel

MODEL = "voyage-4-large"
TEXT_PATH = "retrievalText"
INDEX_NAMES = {
    "service_procedures": "service_procedures_autoembed_v1",
    "procedural_lessons": "procedural_lessons_autoembed_v1",
}
COMMON_FILTERS = (
    "authorityId", "issueIds", "categoryId", "visibility", "current",
    "verificationStatus", "validUntil", "sourceVersion", "knowledgeKind", "id",
)
LESSON_FILTERS = ("portalId", "workflowKind", "formFamily", "formVersions")
INDEX_DOCUMENTATION = "https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/"
QUERY_DOCUMENTATION = "https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/"


def native_index_definition(collection_name: str) -> dict[str, Any]:
    if collection_name not in INDEX_NAMES:
        raise ValueError("Only public procedure/lesson collections may be indexed")
    filters = COMMON_FILTERS + (LESSON_FILTERS if collection_name == "procedural_lessons" else ())
    return {"fields": [
        {"type": "autoEmbed", "modality": "text", "path": TEXT_PATH, "model": MODEL},
        *({"type": "filter", "path": path} for path in filters),
    ]}


def definition_matches(collection_name: str, definition: dict[str, Any]) -> bool:
    """Allow Atlas to materialize defaults; require every configured filter."""
    fields = definition.get("fields", [])
    expected = native_index_definition(collection_name)["fields"]
    for field in expected:
        match = next((f for f in fields if f.get("path") == field["path"]), None)
        if not match or any(match.get(key) != value for key, value in field.items()):
            return False
    embeddings = [f for f in fields if f.get("type") in {"autoEmbed", "vector"}]
    return len(embeddings) == 1 and embeddings[0].get("path") == TEXT_PATH and embeddings[0].get("type") == "autoEmbed"


def inspect_native_index(db: Any, collection_name: str) -> dict[str, Any]:
    name = INDEX_NAMES[collection_name]
    indexes = list(db[collection_name].list_search_indexes(name=name))
    if not indexes:
        return {"indexName": name, "status": "MISSING", "queryable": False, "configurationMatches": False}
    index = indexes[0]
    definition = index.get("latestDefinition", {})
    reported = next((f for f in definition.get("fields", []) if f.get("type") == "autoEmbed"), {})
    node_settings = []
    node_definitions_match = True
    for node in index.get("statusDetail", []):
        active = (node.get("mainIndex") or {}).get("definition")
        if active:
            node_definitions_match &= definition_matches(collection_name, active)
            embed = next((f for f in active.get("fields", []) if f.get("type") == "autoEmbed"), {})
            node_settings.append({
                "status": node.get("status"), "queryable": node.get("queryable"),
                "settings": {key: embed[key] for key in ("model", "numDimensions", "quantization", "similarity", "indexingMethod") if key in embed},
            })
    # Reported settings and documentation defaults remain separate evidence.
    return {
        "indexName": name,
        "type": index.get("type"),
        "status": index.get("status", "UNKNOWN"),
        "queryable": bool(index.get("queryable", False)),
        "configurationMatches": definition_matches(collection_name, definition) and node_definitions_match,
        "definitionVersion": index.get("latestDefinitionVersion"),
        "definition": deepcopy(definition),
        "model": reported.get("model"),
        "reportedSettings": {key: reported[key] for key in ("numDimensions", "quantization", "similarity", "indexingMethod") if key in reported},
        "effectiveNodeSettings": node_settings,
        "documentedDefaults": {"numDimensions": 1024, "quantization": "scalar", "indexingMethod": "hnsw"},
        "documentation": INDEX_DOCUMENTATION,
    }


def ensure_native_indexes(db: Any) -> list[dict[str, Any]]:
    """Create missing indexes only. A mismatch requires an explicit migration."""
    outcomes = []
    for collection_name, index_name in INDEX_NAMES.items():
        if collection_name not in db.list_collection_names():
            db.create_collection(collection_name)
        state = inspect_native_index(db, collection_name)
        if state["status"] == "MISSING":
            db[collection_name].create_search_index(SearchIndexModel(
                definition=native_index_definition(collection_name),
                name=index_name,
                type="vectorSearch",
            ))
            outcomes.append({"collection": collection_name, "indexName": index_name, "created": True, "status": "PENDING"})
        elif not state["configurationMatches"]:
            raise ValueError(f"Native index configuration mismatch: {collection_name}/{index_name}; migration required")
        else:
            outcomes.append({"collection": collection_name, "created": False, **state})
    return outcomes
