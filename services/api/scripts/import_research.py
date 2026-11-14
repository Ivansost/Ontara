#!/usr/bin/env python3
"""Validate and idempotently import a Roads research batch into the event Atlas."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.models import ResearchBatch
from app.research import ResearchImporter
from app.storage import ArtifactStore, Store


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    batch = ResearchBatch.model_validate_json(Path(args.file).read_text())
    if args.validate_only:
        print(json.dumps({"batchId": batch.batch_id, "valid": True, "procedures": len(batch.procedures), "sources": len(batch.sources)}))
        return 0
    settings = Settings.load(args.env_file)
    store = Store.connect(settings)
    store.ensure_indexes()
    result = ResearchImporter(store, ArtifactStore(store.db, settings.max_artifact_bytes)).import_batch(batch)
    print(json.dumps(result, default=str, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Print only type, not a potentially credential-bearing connection string.
        print(json.dumps({"status": "failed", "errorType": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
