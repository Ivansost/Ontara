#!/usr/bin/env python3
"""Search-verify imported public procedure versions, never generate vectors."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.retrieval import retrieve_procedures, verify_record_search


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config/ontara/mongodb.env")
    parser.add_argument("--input", type=Path, required=True, help="The validated ResearchBatch JSON that was actually imported")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    evidence = {"batchId": payload["batchId"], "checkedAt": datetime.now(timezone.utc).isoformat(), "procedures": [], "authorities": []}
    env = dotenv_values(args.env_file) if args.env_file.exists() else {}
    uri = os.environ.get("MONGODB_URI") or env.get("MONGODB_URI")
    if not uri:
        evidence.update({"status": "assistance_required", "reason": "MONGODB_URI missing"})
    else:
        try:
            with MongoClient(uri, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000, tz_aware=True) as client:
                db = client["ontara"]
                imported = db["import_runs"].find_one({"id": payload["batchId"]})
                if not imported or imported.get("status") != "completed":
                    raise ValueError("The validated batch has not completed import")
                seen = set()
                for procedure in payload.get("procedures", []):
                    if procedure.get("verificationStatus") != "verified" or not procedure.get("current", True):
                        evidence["procedures"].append({"id": procedure["id"], "status": "excluded", "reason": "Not current verified public knowledge"})
                        continue
                    proof = verify_record_search(db, "service_procedures", procedure["id"], expected_source_version=procedure["sourceVersion"])
                    evidence["procedures"].append(proof)
                    authority = procedure["authorityId"]
                    if authority not in seen:
                        seen.add(authority)
                        result = retrieve_procedures(db, procedure["retrievalText"][:8000], authority, procedure["issueIds"][0])
                        evidence["authorities"].append({"authorityId": authority, **result})
                checked = [item for item in evidence["procedures"] if item["status"] != "excluded"]
                evidence["counts"] = {"authoritiesChecked": len(evidence["authorities"]), "proceduresChecked": len(checked), "searchableRecords": sum(item["status"] == "ready" for item in checked), "excludedRecords": len(evidence["procedures"]) - len(checked)}
                evidence["status"] = "ready" if checked and evidence["authorities"] and all(x["status"] == "ready" for x in [*checked, *evidence["authorities"]]) else "pending"
                # Keep the original import outcome and add independent search proof.
                db["import_runs"].update_one({"id": payload["batchId"]}, {"$set": {"searchStatus": evidence["status"], "searchVerification": evidence}}, upsert=False)
        except (PyMongoError, ValueError) as exc:
            evidence.update({"status": "assistance_required", "errorType": type(exc).__name__, "errorCode": getattr(exc, "code", None)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(json.dumps({"batchId": evidence["batchId"], "status": evidence["status"], "proceduresChecked": len(evidence["procedures"]), "authoritiesChecked": len(evidence["authorities"])}))
    return 0 if evidence["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
