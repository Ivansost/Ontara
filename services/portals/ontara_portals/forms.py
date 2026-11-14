"""The receiver publishes its forms; the executor must observe these forms."""

from dataclasses import dataclass, asdict
import hashlib
import json
import re


PORTALS = {
    "roads": {
        "title": "Regional Roads Portal — DEMO",
        "authorityId": "halton-region",
        "routeId": "halton-roads-demo",
        "issueId": "pothole",
        "fixtureId": "halton-regional-road",
        "description": "Synthetic Halton regional-road pothole reports. This is an independent test receiver; it does not contact Halton Region.",
    },
    "graffiti": {
        "title": "Local Municipality Portal — DEMO",
        "authorityId": "milton-town",
        "routeId": "milton-graffiti-demo",
        "issueId": "public-wall-graffiti",
        "fixtureId": "milton-public-wall",
        "description": "Synthetic Milton public-wall graffiti reports. This is an independent test receiver; it does not contact the Town of Milton.",
    },
}


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    options: tuple[str, ...] = ()
    default: str = ""
    max_length: int = 500


def fields_for(portal_id: str, action: str, version: int) -> list[Field]:
    if portal_id not in PORTALS or action not in {"create", "update"}:
        raise ValueError("Unknown portal or action")
    if action == "create":
        fields = [Field("location", "Incident location", required=True), Field("description", "Describe the problem", "textarea", True, max_length=4000)]
        if portal_id == "graffiti":
            fields += [
                Field("surfaceType", "Public structure", "select", True, ("Public wall", "Underpass"), "Public wall"),
                Field("offensiveContent", "Does it contain offensive content?", "select", True, ("Yes", "No", "Not sure"), "Not sure"),
            ]
        return fields + [Field("reporterName", "Your name (optional)"), Field("contactEmail", "Controlled test email (optional)", "email", max_length=254), Field("observedAt", "Date observed (optional)", "date", max_length=10)]
    if portal_id == "roads" and version == 2:
        return [
            Field("roadIntersection", "Road or intersection", required=True),
            Field("travelDirection", "Direction of travel", "select", True, ("Northbound", "Southbound", "Eastbound", "Westbound", "Not sure")),
            Field("roadPosition", "Position on the road", "select", True, ("In travel lane", "On shoulder", "At curb", "Not sure")),
            Field("nearestLandmark", "Nearest landmark", required=True),
            Field("additionalDetails", "Additional details (optional)", "textarea", max_length=4000),
        ]
    return [Field("location", "Incident location", required=True), Field("additionalDetails", "Additional details (optional)", "textarea", max_length=4000)]


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def form_schema(portal_id: str, action: str, version: int) -> dict:
    schema = {"portalId": portal_id, "action": action, "formVersion": version, "fields": [asdict(field) for field in fields_for(portal_id, action, version)]}
    # Form version applies to the unfinished update, never retroactively to creation.
    schema["snapshotDigest"] = canonical_digest(schema)
    return schema


def validate_values(portal_id: str, action: str, version: int, values: dict) -> dict[str, str]:
    fields = fields_for(portal_id, action, version)
    known = {field.name for field in fields}
    if set(values) - known:
        raise ValueError("Unexpected form fields: " + ", ".join(sorted(set(values) - known)))
    result = {}
    for field in fields:
        raw = values.get(field.name, field.default)
        if not isinstance(raw, str):
            raise ValueError(f"{field.label} must be text")
        value = raw.strip()
        if field.required and not value:
            raise ValueError(f"{field.label} is required")
        if len(value) > field.max_length:
            raise ValueError(f"{field.label} is too long")
        if value and field.options and value not in field.options:
            raise ValueError(f"Choose a listed option for {field.label}")
        if value and field.kind == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid controlled test email")
        if value and field.kind == "date":
            from datetime import date
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Date observed must be a calendar date") from exc
        result[field.name] = value
    return result
