"""Validate the public selector directory; no network, Atlas or application writes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "contracts/municipalities.json"
MANIFEST = ROOT / "data/municipal/municipality-options.sources.json"
COUNTS = {"total": 444, "lowerTier": 241, "singleTier": 173, "upperTier": 30}
TIERS = {"Lower Tier": "lower", "Single Tier": "single", "Upper Tier": "upper"}
FIELDS = {"id", "label", "name", "tier", "type", "upperTierId", "upperTierName", "geographicArea", "aliases"}
SUFFIX = re.compile(r", (Township|Municipality|City|Town|Village|County|Regional Municipality|District Municipality|United Counties) of$")


class AnchorText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, text: str) -> None:
        self.parts.append(text)


def plain_name(value: str) -> str:
    parser = AnchorText()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def sort_key(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sort_key(value)).strip("-")


def imported_municipalities() -> dict[tuple[str, str], dict]:
    """Use public research metadata only, preserving every imported identifier."""
    paths = sorted((ROOT / "data/municipal").glob("roads-batch-0[1-4]-20261114.json"))
    paths.append(ROOT / "data/municipal/roads-boundaries-20261114.json")
    records: dict[tuple[str, str], dict] = {}
    for path in paths:
        for row in json.loads(path.read_text())["municipalities"]:
            key = (row["name"], row["type"].removesuffix("-tier"))
            if key in records and records[key]["id"] != row["id"]:
                raise ValueError(f"Conflicting imported identifiers: {key}")
            records[key] = {field: row.get(field) for field in ("id", "parentId")}
    return records


def display_name(name: str, kind: str) -> str:
    if kind == "regional-municipality":
        return f"{name} Region"
    if kind == "district-municipality":
        return f"{name} District Municipality"
    if kind == "united-counties":
        return f"United Counties of {name}"
    if kind == "county" and not name.endswith(" County"):
        return f"{name} County"
    return name


def build_options(source_bytes: bytes, imported: dict[tuple[str, str], dict]) -> list[dict]:
    """Deterministic English registry transformation, also used for source checks."""
    reader = csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig")))
    if reader.fieldnames != ["Municipality", "Municipal status", "Geographic area"]:
        raise ValueError("Unexpected Ontario registry columns")
    records = []
    for row in reader:
        full = plain_name(row["Municipality"])
        suffix = SUFFIX.search(full)
        name = full[:suffix.start()] if suffix else full
        kind = suffix.group(1).lower().replace(" ", "-") if suffix else ("county" if full.endswith(" County") else "municipality")
        tier = TIERS[row["Municipal status"]]
        existing = imported.get((full, tier))
        id_suffix = {"regional-municipality": "region", "district-municipality": "district", "united-counties": "counties"}.get(kind, kind)
        identifier = existing["id"] if existing else slug(name if slug(name).endswith("-" + id_suffix) else name + " " + id_suffix)
        records.append({"id": identifier, "name": name, "tier": tier, "type": kind, "geographicArea": row["Geographic area"], "fullName": full, "displayName": display_name(name, kind)})
    uppers = {row["geographicArea"]: row for row in records if row["tier"] == "upper"}
    if len(uppers) != 30:
        raise ValueError("Expected 30 distinct upper-tier geographic areas")
    options = []
    for row in records:
        parent = uppers.get(row["geographicArea"]) if row["tier"] == "lower" else None
        if row["tier"] == "lower" and parent is None:
            raise ValueError(f"No upper-tier member match: {row['fullName']}")
        aliases = [row["fullName"]]
        suffix = SUFFIX.search(row["fullName"])
        if suffix:
            aliases.append(f"{suffix.group(1)} of {row['name']}")
        options.append({
            "id": row["id"],
            "label": f"{row['displayName']}, {parent['displayName']}" if parent else row["displayName"],
            "name": row["name"],
            "tier": row["tier"],
            "type": row["type"],
            "upperTierId": parent["id"] if parent else None,
            "upperTierName": parent["displayName"] if parent else None,
            "geographicArea": row["geographicArea"],
            "aliases": list(dict.fromkeys(aliases)),
        })
    return sorted(options, key=lambda row: (sort_key(row["label"]), row["id"]))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(source_csv: Path | None = None) -> dict:
    raw = DIRECTORY.read_bytes()
    directory = json.loads(raw)
    manifest = json.loads(MANIFEST.read_text())
    options = directory["options"]
    check(directory["version"] == 1, "Unexpected directory contract version")
    check(hashlib.sha256(raw).hexdigest() == manifest["directory"]["sha256"], "Directory does not match frozen provenance hash")
    check(directory["source"] == manifest["source"], "Directory and provenance source disagree")
    check(directory["counts"] == COUNTS, "Unexpected official registry counts")
    counts = Counter(row["tier"] for row in options)
    check({"total": len(options), "lowerTier": counts["lower"], "singleTier": counts["single"], "upperTier": counts["upper"]} == COUNTS, "Option counts do not match registry")
    by_id = {row["id"]: row for row in options}
    check(len(by_id) == len(options), "Duplicate municipality identifiers")
    check(len({row["label"].casefold() for row in options}) == len(options), "Duplicate display labels")
    check(options == sorted(options, key=lambda row: (sort_key(row["label"]), row["id"])), "Options are not alphabetized")
    for row in options:
        check(set(row) == FIELDS, f"Unexpected fields: {row['id']}")
        check(bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row["id"])), f"Invalid identifier: {row['id']}")
        check(row["aliases"] and len(row["aliases"]) == len(set(row["aliases"])), f"Invalid aliases: {row['id']}")
        for field in ("name", "label", "type", "geographicArea"):
            check(isinstance(row[field], str) and bool(row[field].strip()), f"Missing {field}: {row['id']}")
        if row["tier"] == "lower":
            parent = by_id.get(row["upperTierId"])
            check(parent is not None and parent["tier"] == "upper", f"Invalid parent: {row['id']}")
            check(parent["label"] == row["upperTierName"] and parent["geographicArea"] == row["geographicArea"], f"Incorrect upper-tier membership: {row['id']}")
        else:
            check(row["upperTierId"] is None and row["upperTierName"] is None, f"Non-lower tier has a parent: {row['id']}")
    imported = imported_municipalities()
    check(len(imported) == 207, "Expected the existing 207 imported municipality identifiers")
    for (full, tier), previous in imported.items():
        current = by_id.get(previous["id"])
        check(current is not None and current["tier"] == tier and full in current["aliases"], f"Imported identifier changed: {previous['id']}")
        check(current["upperTierId"] == previous["parentId"], f"Imported parent changed: {previous['id']}")
    check(by_id["milton-town"]["label"] == "Milton, Halton Region", "Milton demo label changed")
    check(by_id["milton-town"]["upperTierId"] == "halton-region", "Milton demo parent changed")
    check(by_id["toronto-city"]["upperTierId"] is None and by_id["hamilton-city"]["upperTierId"] is None, "Single-tier cities must not receive a parent")
    check(by_id["hamilton-township"]["upperTierId"] == "northumberland-county", "Hamilton township confused with Hamilton city")
    if source_csv is not None:
        source_bytes = source_csv.read_bytes()
        check(hashlib.sha256(source_bytes).hexdigest() == directory["source"]["sha256"], "CSV bytes differ from the verified source snapshot")
        check(options == build_options(source_bytes, imported), "Directory differs from the complete official registry transformation")
    return {"valid": True, **COUNTS, "preservedImportedIds": len(imported), "sourceCsvCompared": source_csv is not None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, help="Also compare every option with the downloaded official CSV; no network requests are made.")
    args = parser.parse_args()
    print(json.dumps(validate(args.source_csv), indent=2))
