"""Versioned authored navigation and questions shared by every intake channel."""
from __future__ import annotations

from copy import deepcopy

CATALOGUE_VERSION = "2026-11-14.1"
INACTIVE_REASON = "Not available in this demo. You can browse this service, but reports and personal details are not collected."


def node(id: str, label: str, kind: str, children: list | None = None, *, active: bool = False, slug: str | None = None) -> dict:
    return {"id": id, "slug": slug or id.split("-")[-1], "label": label,
            "description": "", "kind": kind, "available": active,
            "disabledReason": None if active else INACTIVE_REASON,
            "questionSchemaId": id if kind == "issue" and active else None,
            "children": children or []}


def issue(id: str, label: str, active: bool = False, slug: str | None = None) -> dict:
    return node(id, label, "issue", active=active, slug=slug)


def group(id: str, label: str, children: list, active: bool = False, slug: str | None = None) -> dict:
    return node(id, label, "group", children, active=active, slug=slug)


def inactive(category_id: str, label: str, groups: list[tuple[str, str, list[tuple[str, str]]]]) -> dict:
    return node(category_id, label, "category", [
        group(f"{category_id}-{gid}", glabel, [issue(f"{category_id}-{iid}", ilabel, slug=iid) for iid, ilabel in leaves], slug=gid)
        for gid, glabel, leaves in groups
    ], slug=category_id)


CATEGORIES = [
    node("roads", "Roads, Sidewalks & Traffic", "category", [
        group("roads-road-surface", "Road surface", [issue("roads-pothole", "Pothole", True, "pothole"), issue("roads-pavement", "Broken or uneven pavement", True, "pavement")], True, "road-surface"),
        group("roads-obstructions", "Obstructions & debris", [group("roads-debris", "Debris", [issue("roads-debris-loose", "Loose material", True, "loose-material"), issue("roads-debris-object", "Larger object", True, "larger-object")], True, "debris")], True, "obstructions"),
        group("roads-sidewalks-curbs", "Sidewalks & curbs", [issue("roads-sidewalk", "Cracked or uneven sidewalk", True, "sidewalk"), issue("roads-curb", "Damaged curb", True, "curb")], True, "sidewalks-curbs"),
        group("roads-signs-safety", "Signs & road safety", [issue("roads-sign", "Damaged or missing sign", True, "sign"), issue("roads-safety", "Unsafe intersection or crossing", True, "safety")], True, "signs-safety"),
    ], active=True, slug="roads"),
    node("graffiti", "Graffiti", "category", [
        group("graffiti-public-structures", "Public structures", [issue("graffiti-wall", "Wall or underpass", True, "wall"), issue("graffiti-building", "Public building", True, "building")], True, "public-structures"),
        group("graffiti-street-furniture", "Street furniture", [issue("graffiti-bench-bin", "Bench or public bin", True, "bench-bin"), issue("graffiti-shelter", "Shelter or other public fixture", True, "shelter")], True, "street-furniture"),
        group("graffiti-private-property", "Private property", [issue("graffiti-private-wall", "Building or wall", True, "building-wall"), issue("graffiti-fence", "Fence", True, "fence")], True, "private-property"),
    ], active=True, slug="graffiti"),
    inactive("waste", "Waste, Bins & Litter", [
        ("collection", "Collection", [("missed-collection", "Missed collection"), ("collection-concern", "Collection-related concern")]),
        ("bins", "Bins", [("damaged-bin", "Damaged bin"), ("overflowing-bin", "Overflowing public bin")]),
        ("litter-dumping", "Litter & dumping", [("litter", "Litter"), ("dumped-items", "Illegally dumped items")]),
    ]),
    inactive("trees", "Trees & Vegetation", [
        ("fallen-material", "Fallen material", [("fallen-branch", "Fallen branch"), ("fallen-tree", "Fallen tree")]),
        ("condition", "Tree condition", [("damaged-tree", "Damaged tree"), ("tree-health", "Tree health concern")]),
        ("vegetation", "Vegetation", [("overgrowth", "Overgrowth"), ("obstructing-branches", "Obstructing branches")]),
    ]),
    inactive("water", "Water, Sewers & Spills", [
        ("water", "Water", [("visible-leak", "Visible leak"), ("no-water", "No-water concern")]),
        ("drainage", "Sewers & drainage", [("blocked-catch-basin", "Blocked catch basin"), ("sewer-backup", "Sewer backup")]),
        ("spills", "Spills", [("roadway-spill", "Roadway spill"), ("waterway-spill", "Waterway spill")]),
    ]),
    inactive("parks", "Parks & Public Facilities", [
        ("playgrounds-sports", "Playgrounds & sports", [("damaged-equipment", "Damaged equipment"), ("damaged-court-field", "Damaged court or field")]),
        ("amenities", "Buildings & amenities", [("washroom", "Washroom issue"), ("damaged-fixture", "Damaged park fixture")]),
    ]),
    inactive("snow", "Snow & Ice", [
        ("roads", "Roads", [("snow-clearing", "Snow-clearing concern"), ("icy-road", "Icy roadway")]),
        ("paths", "Sidewalks & paths", [("uncleared-sidewalk", "Uncleared sidewalk"), ("icy-path", "Icy path")]),
    ]),
    inactive("bylaws", "Noise, Bylaws & Property", [
        ("noise", "Noise", [("construction-noise", "Construction"), ("amplified-sound", "Amplified sound"), ("other-noise", "Other non-urgent noise")]),
        ("property", "Property conditions", [("maintenance", "Maintenance concern"), ("obstruction", "Obstruction")]),
        ("parking", "Parking concerns", [("parking-violation", "Suspected parking violation"), ("blocked-access", "Blocked access")]),
    ]),
    inactive("animals", "Animals & Pests", [
        ("animals", "Animals", [("dead-animal", "Dead animal"), ("animal-concern", "Non-urgent animal concern")]),
        ("dogs-pets", "Dogs & pets", [("off-leash", "Off-leash concern"), ("animal-nuisance", "Animal-related nuisance")]),
        ("pests", "Pests", [("pest-concern", "Pest concern"), ("tree-insects", "Tree-related insects")]),
    ]),
]


def flatten(nodes: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in nodes:
        result[item["id"]] = item
        result.update(flatten(item["children"]))
    return result


NODES = flatten(CATEGORIES)
ROAD_ISSUES = tuple(key for key, value in NODES.items() if key.startswith("roads-") and value["kind"] == "issue")
GRAFFITI_ISSUES = tuple(key for key, value in NODES.items() if key.startswith("graffiti-") and value["kind"] == "issue")


def select(id: str, label: str, values: list[str], required: bool = True, description: str = "") -> dict:
    return {"id": id, "type": "select", "label": label, "required": required, "description": description,
            "options": [{"value": v, "label": v} for v in values]}


DANGER = select("immediateDanger", "Is there an immediate danger?", ["No", "Yes", "Not sure"], description="Stay clear of traffic. Immediate danger needs urgent assistance, rather than an ordinary report.")
DESCRIPTION = {"id": "description", "type": "textarea", "label": "What did you notice?", "required": True, "minLength": 10, "maxLength": 2000, "description": "Describe what you observed. Do not enter traffic or measure the damage."}
DATE = {"id": "observedAt", "type": "date", "label": "When did you notice it?", "required": False, "description": "Leave blank if you are not sure."}
POSITION = select("roadPosition", "Where on the road?", ["In travel lane", "On shoulder", "At curb", "Not sure"])
DIRECTION = select("travelDirection", "Which direction or side?", ["Northbound", "Southbound", "Eastbound", "Westbound", "Not sure"])
LANDMARK = {"id": "nearestLandmark", "type": "text", "label": "What is the nearest landmark?", "required": True, "minLength": 2, "maxLength": 300, "description": "The receiving demo portal now needs this detail. Enter only something you know."}
FOLLOW_UP_QUESTIONS = {"nearestLandmark": LANDMARK}

QUESTIONS: dict[str, dict] = {}
for iid in ROAD_ISSUES:
    q = [DANGER, POSITION, DIRECTION, DATE, DESCRIPTION]
    if iid == "roads-sign":
        q = [DANGER, select("signType", "Which sign is affected?", ["Stop sign", "Yield sign", "Street name", "Other", "Not sure"]), *q[1:]]
    if iid == "roads-safety":
        q = [DANGER, select("safetyConcern", "What concerns you?", ["Crossing visibility", "Vehicle speed", "Intersection layout", "Other", "Not sure"]), DATE, DESCRIPTION]
    if iid == "roads-sidewalk":
        q = [DANGER, select("sidewalkPosition", "Where is the sidewalk defect?", ["Along the sidewalk", "At a crossing", "At a driveway", "Not sure"]), DATE, DESCRIPTION]
    if iid == "roads-curb":
        q = [DANGER, select("curbPosition", "Where is the damaged curb?", ["Along the road edge", "At a crossing", "At a driveway", "Not sure"]), DATE, DESCRIPTION]
    QUESTIONS[iid] = {"issueId": iid, "version": CATALOGUE_VERSION, "questions": deepcopy(q)}

for iid in GRAFFITI_ISSUES:
    surfaces = {"graffiti-wall": ["Public wall", "Underpass"], "graffiti-building": ["Public building"],
                "graffiti-bench-bin": ["Bench", "Public bin"], "graffiti-shelter": ["Shelter", "Other fixture"],
                "graffiti-private-wall": ["Private building", "Private wall"], "graffiti-fence": ["Fence"]}[iid]
    q = [DANGER, select("surfaceType", "Which surface is affected?", surfaces),
         select("offensiveContent", "Does it contain offensive content?", ["Yes", "No", "Not sure"]), DATE, DESCRIPTION]
    if iid in {"graffiti-private-wall", "graffiti-fence"}:
        q.append(select("ownershipRelationship", "What is your relationship to the property?", ["Owner", "Tenant", "Neither", "Not sure"]))
    QUESTIONS[iid] = {"issueId": iid, "version": CATALOGUE_VERSION, "questions": deepcopy(q)}

for questionnaire in QUESTIONS.values():
    for question in questionnaire["questions"]:
        if question["id"] != "immediateDanger":
            question["visibleWhen"] = {"questionId": "immediateDanger", "equals": "No"}

DEMO_LOCATIONS = [
    {"id": "halton-regional-road", "fixtureId": "halton-regional-road", "label": "Halton regional road — synthetic demo location",
     "municipalityId": "milton-town", "municipalityName": "Milton", "upperTierId": "halton-region", "upperTierName": "Halton Region",
     "incidentAddress": "Regional Road 25 at Louis St. Laurent Avenue, Milton", "categoryId": "roads", "demo": True},
    {"id": "milton-public-wall", "fixtureId": "milton-public-wall", "label": "Milton public wall — synthetic demo location",
     "municipalityId": "milton-town", "municipalityName": "Milton", "upperTierId": "halton-region", "upperTierName": "Halton Region",
     "incidentAddress": "Synthetic municipal public wall, Milton", "categoryId": "graffiti", "demo": True},
]


def get_catalogue() -> dict:
    return {"version": CATALOGUE_VERSION, "categories": deepcopy(CATEGORIES), "demoLocations": deepcopy(DEMO_LOCATIONS),
            "disclaimer": "Two controlled demo portals. Researched municipal procedures do not establish live submission support."}


def get_questions(issue_id: str) -> dict | None:
    return deepcopy(QUESTIONS.get(issue_id))
