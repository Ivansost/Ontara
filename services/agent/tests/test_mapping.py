import pytest
from ontara_agent.mapping import MappingError, MappingProposal, approved_facts, initial_mapping, validate_proposal


def form():
    return {"fingerprint": "a" * 64, "formVersion": "2", "fields": [
        {"name": "roadIntersection", "label": "Road or intersection", "type": "text", "required": True},
        {"name": "travelDirection", "label": "Travel direction", "type": "select-one", "required": True, "options": ["Northbound", "Not sure"]},
        {"name": "nearestLandmark", "label": "Nearest landmark", "type": "text", "required": True},
    ]}


def lesson():
    return [{"id": "verified-1", "verified": True, "current": True, "visibility": "public", "knowledgeKind": "verified_rehearsal"}]


def proposal(**changes):
    return MappingProposal.model_validate({"formFingerprint": "a" * 64, "lessonIds": ["verified-1"], "mappings": [{"fieldName": "roadIntersection", "factId": "location"}, {"fieldName": "travelDirection", "factId": "travelDirection"}], "missingFacts": [{"fieldName": "nearestLandmark", "questionId": "nearestLandmark"}], "explanation": "The current form requires an absent approved landmark.", **changes})


def test_missing_fact_uses_authored_question_without_inventing_value():
    values, missing = validate_proposal(proposal(), form(), {"location": "Synthetic road", "travelDirection": "Northbound"}, lesson())
    assert values == {"roadIntersection": "Synthetic road", "travelDirection": "Northbound"}
    assert missing == ["nearestLandmark"]


@pytest.mark.parametrize("records", [[], [{"id": "verified-1", "verified": False, "knowledgeKind": "seeded_demo"}], [{"id": "verified-1", "verified": True, "knowledgeKind": "diagnostic"}], [{"id": "verified-1", "verified": True, "current": False, "knowledgeKind": "verified_rehearsal"}]])
def test_lesson_withheld_unverified_or_stale_blocks_mapping(records):
    with pytest.raises(MappingError):
        validate_proposal(proposal(), form(), {"location": "Synthetic road", "travelDirection": "Northbound"}, records)


def test_unknown_or_changed_facts_cannot_be_generated_by_mapper():
    p = proposal(mappings=[{"fieldName": "roadIntersection", "factId": "invented"}])
    with pytest.raises(MappingError):
        validate_proposal(p, form(), {"location": "Synthetic road"}, lesson())


def test_current_select_options_are_enforced():
    with pytest.raises(MappingError):
        validate_proposal(proposal(), form(), {"location": "Synthetic road", "travelDirection": "Westbound"}, lesson())


def test_changed_form_cannot_reuse_initial_hardcoded_adapter():
    with pytest.raises(MappingError):
        initial_mapping(form(), {"location": "Synthetic road"})


def test_contact_requires_approved_consent_and_facts_are_immutable():
    payload = {"location": {"incidentAddress": "Synthetic road"}, "answers": {"description": "Synthetic damage"}, "reporter": {"name": "Synthetic resident", "email": "test@example.invalid", "contactConsent": False}}
    facts = approved_facts(payload)
    assert "reporterName" not in facts and "contactEmail" not in facts
    assert facts["location"] == "Synthetic road"
    assert payload["answers"] == {"description": "Synthetic damage"}
