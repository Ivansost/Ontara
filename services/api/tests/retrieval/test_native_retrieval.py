from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock

import pytest
from pymongo.errors import OperationFailure

from app.retrieval.indexes import INDEX_NAMES, MODEL, definition_matches, native_index_definition
from app.retrieval.lessons import ProceduralLesson, promote_lesson
from app.retrieval.service import build_text_pipeline, retrieve_lessons, retrieve_procedures, text_hash, verify_record_search


def procedure(**changes):
    record = {
        "_id": "p1", "id": "p1", "authorityId": "halton-region", "issueIds": ["roads-pothole"],
        "categoryId": "roads", "visibility": "public", "current": True, "verificationStatus": "verified",
        "sourceVersion": "v1", "retrievalText": "Report a regional road pothole using the published official procedure.",
        "sourceIds": ["s1"], "verifiedAt": datetime.now(timezone.utc) - timedelta(minutes=1),
        "searchStatus": "ready", "integrationStatus": "research_only",
    }
    record.update(changes)
    record["searchVerification"] = {
        "nativeQuery": True, "sourceVersion": record["sourceVersion"],
        "retrievalTextHash": text_hash(record["retrievalText"]), "indexName": INDEX_NAMES["service_procedures"],
    }
    return record


def lesson(**changes):
    record = procedure(id="lesson1", _id="lesson1", portalId="roads", workflowKind="ticket_update",
                       formFamily="roads-follow-up", formVersions=["2"], knowledgeKind="verified_rehearsal",
                       evidenceRefs=["operation1"], procedure=["Request the missing landmark before approval."])
    record["searchVerification"]["indexName"] = INDEX_NAMES["procedural_lessons"]
    record.update(changes)
    return record


def database(record, *, collection_name="service_procedures", raw=None, status="READY", queryable=True):
    collections = {name: MagicMock() for name in [*INDEX_NAMES, "source_references", "operations", "cases", "procedural_lesson_versions"]}
    db = MagicMock()
    db.__getitem__.side_effect = collections.__getitem__
    coll = collections[collection_name]
    coll.list_search_indexes.return_value = [{
        "name": INDEX_NAMES[collection_name], "type": "vectorSearch", "status": status,
        "queryable": queryable, "latestDefinition": native_index_definition(collection_name),
    }]
    coll.aggregate.return_value = [dict(record, score=0.93)] if raw is None else raw
    cursor = MagicMock()
    cursor.__iter__.side_effect = lambda: iter([{"id": record["id"], "sourceVersion": record["sourceVersion"]}])
    cursor.limit.return_value = cursor
    coll.find.return_value = cursor
    coll.find_one.side_effect = lambda criteria: deepcopy(record) if criteria.get("id", criteria.get("_id")) == record["id"] else None
    coll.update_one.return_value.matched_count = 1
    collections["source_references"].find_one.return_value = {"id": "s1", "authorityId": "halton-region", "verificationStatus": "verified"}
    collections["procedural_lesson_versions"].find_one.return_value = None
    return db, collections


def search_procedures(db):
    return retrieve_procedures(db, "road pothole reporting", "halton-region", "roads-pothole")


def search_lessons(db, **kwargs):
    return retrieve_lessons(db, "changed follow-up requires a landmark", "halton-region", "roads-pothole",
                            portal_id="roads", form_family="roads-follow-up", form_version="2", **kwargs)


def test_pipeline_uses_native_text_only_and_preserves_scope():
    filters = {"authorityId": "halton-region", "issueIds": "roads-pothole"}
    stage = build_text_pipeline("service_procedures", " regional road defect ", filters)[0]["$vectorSearch"]
    assert stage["query"] == {"text": "regional road defect"}
    assert stage["filter"] == filters
    assert stage["exact"] is True
    assert "queryVector" not in stage and "model" not in stage
    assert native_index_definition("service_procedures")["fields"][0] == {
        "type": "autoEmbed", "path": "retrievalText", "modality": "text", "model": MODEL,
    }


def test_ready_procedure_retains_research_only_boundary():
    db, _ = database(procedure())
    result = search_procedures(db)
    assert result["status"] == "ready"
    assert result["candidates"][0]["integrationStatus"] == "research_only"
    assert result["evidence"]["queryExecuted"] is True
    assert result["evidence"]["reranking"]["ran"] is False
    assert "_id" not in result["candidates"][0]
    assert result["evidence"]["pipeline"][0]["$vectorSearch"]["filter"]["$and"][1]["$or"] == [{"id": "p1", "sourceVersion": "v1"}]


def test_index_must_not_embed_any_additional_private_field():
    definition = native_index_definition("service_procedures")
    definition["fields"].append({"type": "autoEmbed", "path": "privateNarrative", "modality": "text", "model": MODEL})
    assert definition_matches("service_procedures", definition) is False


@pytest.mark.parametrize("status,queryable,expected", [("PENDING", False, "pending"), ("BUILDING", False, "pending"), ("STALE", True, "assistance_required"), ("FAILED", False, "assistance_required")])
def test_index_state_cannot_silently_fall_back(status, queryable, expected):
    db, collections = database(procedure(), status=status, queryable=queryable)
    assert search_procedures(db)["status"] == expected
    collections["service_procedures"].aggregate.assert_not_called()


@pytest.mark.parametrize("change", [
    {"authorityId": "another-region"}, {"issueIds": ["roads-sign"]}, {"current": False},
    {"verificationStatus": "partial"}, {"visibility": "case"}, {"categoryId": "graffiti"},
    {"validUntil": datetime.now(timezone.utc) - timedelta(seconds=1)}, {"validUntil": "not-a-date"},
])
def test_current_database_scope_is_revalidated_even_if_index_returns_record(change):
    db, _ = database(procedure(**change))
    result = search_procedures(db)
    assert result["status"] == "assistance_required"
    assert result["candidates"] == []


def test_changed_version_or_text_is_pending():
    original = procedure()
    current = procedure(sourceVersion="v2", retrievalText="Changed approved public procedure text for this region.")
    db, _ = database(current, raw=[dict(original, score=0.95)])
    assert search_procedures(db)["status"] == "pending"


def test_current_text_requires_a_matching_native_version_proof():
    record = procedure()
    record["retrievalText"] += " Newly changed instructions."
    db, _ = database(record)
    assert search_procedures(db)["status"] == "pending"


def test_revoked_source_does_not_remain_executable():
    db, collections = database(procedure())
    collections["source_references"].find_one.return_value = {"id": "s1", "authorityId": "halton-region", "verificationStatus": "partial"}
    assert search_procedures(db)["status"] == "assistance_required"


def test_lesson_withheld_changes_ready_path_to_policy_pause():
    db, _ = database(lesson(), collection_name="procedural_lessons")
    available = search_lessons(db)
    withheld = search_lessons(db, withhold_lesson_ids=["lesson1"])
    assert available["status"] == "ready"
    assert withheld["status"] == "assistance_required"
    assert withheld["candidates"] == []
    assert withheld["evidence"]["rejected"][0]["reason"] == "withheld_for_policy_comparison"


def test_portal_integer_form_version_matches_string_lesson_contract():
    db, _ = database(lesson(), collection_name="procedural_lessons")
    result = retrieve_lessons(db, "changed follow-up", "halton-region", "roads-pothole", portal_id="roads", form_family="roads-follow-up", form_version=2)
    assert result["status"] == "ready"
    assert result["evidence"]["pipeline"][0]["$vectorSearch"]["filter"]["$and"][0]["formVersions"] == "2"


@pytest.mark.parametrize("change", [{"formVersions": ["1"]}, {"portalId": "graffiti"}, {"knowledgeKind": "diagnostic"}, {"evidenceRefs": []}])
def test_unusable_lesson_is_rejected(change):
    db, _ = database(lesson(**change), collection_name="procedural_lessons")
    assert search_lessons(db)["status"] == "assistance_required"


def test_no_candidates_is_assistance_and_never_hardcoded_mapping():
    db, _ = database(lesson(), collection_name="procedural_lessons", raw=[])
    result = search_lessons(db)
    assert result["status"] == "assistance_required"
    assert result["candidates"] == []
    assert "mapping" not in result


def test_database_errors_are_safe_and_visible():
    db, collections = database(procedure())
    collections["service_procedures"].aggregate.side_effect = OperationFailure("mongodb+srv://secret:password@private.example", code=13)
    result = search_procedures(db)
    assert result["status"] == "assistance_required"
    encoded = json.dumps(result, default=str)
    assert "secret" not in encoded and "password" not in encoded and "private.example" not in encoded
    assert result["evidence"]["errorCode"] == 13


def test_native_version_proof_is_conditional_on_unchanged_record():
    record = procedure(searchStatus="pending")
    db, collections = database(record)
    result = verify_record_search(db, "service_procedures", "p1")
    assert result["status"] == "ready"
    pipeline = collections["service_procedures"].aggregate.call_args.args[0]
    assert pipeline[0]["$vectorSearch"]["filter"]["sourceVersion"] == "v1"
    update_filter = collections["service_procedures"].update_one.call_args.args[0]
    assert update_filter == {"_id": "p1", "sourceVersion": "v1", "retrievalText": record["retrievalText"]}
    collections["service_procedures"].update_one.return_value.matched_count = 0
    assert verify_record_search(db, "service_procedures", "p1")["status"] == "pending"


def test_unindexed_current_version_never_marked_ready():
    db, collections = database(procedure(searchStatus="pending"), raw=[])
    assert verify_record_search(db, "service_procedures", "p1")["status"] == "pending"
    collections["service_procedures"].update_one.assert_not_called()


def test_batch_cannot_verify_a_different_version_than_was_imported():
    db, collections = database(procedure(sourceVersion="v2"))
    result = verify_record_search(db, "service_procedures", "p1", expected_source_version="v1")
    assert result["status"] == "assistance_required"
    collections["service_procedures"].aggregate.assert_not_called()


def admitted_lesson():
    return ProceduralLesson(
        id="lesson1", authorityId="halton-region", categoryId="roads", issueIds=["roads-pothole"],
        portalId="roads", formFamily="roads-follow-up", formVersions=["2"], title="Rehearsed follow-up split",
        retrievalText="Inspect current fields and request the missing nearest landmark before an approved existing-ticket update.",
        problem="The follow-up form split location and requires a new fact.",
        procedure=["Map only approved facts.", "Request the missing landmark.", "Verify the existing ticket update."],
        sourceVersion="rehearsal-v1", evidenceRefs=["operation1"],
        verifiedAt=datetime.now(timezone.utc) - timedelta(minutes=1),
    )


def test_lesson_cannot_be_promoted_from_attempt_or_missing_receipt():
    db, collections = database(lesson(), collection_name="procedural_lessons")
    collections["operations"].find_one.return_value = {"state": "dispatch_started"}
    with pytest.raises(ValueError, match="receipt_verified"):
        promote_lesson(db, admitted_lesson())
    collections["procedural_lessons"].replace_one.assert_not_called()


def test_real_update_receipt_is_required_and_seed_label_is_preserved():
    db, collections = database(lesson(), collection_name="procedural_lessons")
    collections["operations"].find_one.return_value = {
        "state": "receipt_verified", "action": "update", "portalId": "roads",
        "route": {"authorityId": "halton-region"}, "payload": {"issueId": "roads-pothole"},
        "receipt": {"action": "update", "portalId": "roads", "formVersion": "2", "receiptId": "r1", "ticketId": "t1"},
    }
    collections["procedural_lessons"].find_one.side_effect = None
    collections["procedural_lessons"].find_one.return_value = None
    value = admitted_lesson().model_copy(update={"knowledge_kind": "seeded_demo"})
    result = promote_lesson(db, value)
    assert result["searchStatus"] == "pending"
    stored = collections["procedural_lessons"].replace_one.call_args.args[1]
    assert stored["knowledgeKind"] == "seeded_demo"
    assert "embedding" not in stored and "queryVector" not in stored


@pytest.mark.parametrize("field,value", [("authorityId", "other-region"), ("issueId", "roads-sign"), ("formVersion", "1")])
def test_lesson_receipt_from_other_scope_cannot_promote(field, value):
    db, collections = database(lesson(), collection_name="procedural_lessons")
    operation = {
        "state": "receipt_verified", "action": "update", "portalId": "roads",
        "route": {"authorityId": "halton-region"}, "payload": {"issueId": "roads-pothole"},
        "receipt": {"action": "update", "portalId": "roads", "formVersion": "2", "receiptId": "r1", "ticketId": "t1"},
    }
    target = operation["route"] if field == "authorityId" else operation["payload"] if field == "issueId" else operation["receipt"]
    target[field] = value
    collections["operations"].find_one.return_value = operation
    with pytest.raises(ValueError, match="matching authority"):
        promote_lesson(db, admitted_lesson())
    collections["procedural_lessons"].replace_one.assert_not_called()
