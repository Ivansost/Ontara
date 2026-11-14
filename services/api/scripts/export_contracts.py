#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalogue import CATALOGUE_VERSION, FOLLOW_UP_QUESTIONS, QUESTIONS, get_catalogue
from app.models import CaseView, CatalogueView, Questionnaire, ResearchBatch, RouteDecision

root = Path(__file__).resolve().parents[3] / "contracts"
root.mkdir(exist_ok=True)
payloads = {"catalogue.json": get_catalogue(), "questions.json": {"version": CATALOGUE_VERSION, "issues": QUESTIONS, "followUp": FOLLOW_UP_QUESTIONS},
            "research-import.schema.json": ResearchBatch.model_json_schema(by_alias=True),
            "catalogue.schema.json": CatalogueView.model_json_schema(by_alias=True),
            "case.schema.json": CaseView.model_json_schema(by_alias=True),
            "questionnaire.schema.json": Questionnaire.model_json_schema(by_alias=True),
            "route.schema.json": RouteDecision.model_json_schema(by_alias=True)}
for name, value in payloads.items():
    (root / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
CatalogueView.model_validate(payloads["catalogue.json"])
for questionnaire in QUESTIONS.values():
    Questionnaire.model_validate(questionnaire)
try:
    from app.main import create_app
except ImportError:
    pass
else:
    (root / "openapi.json").write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
print(f"Exported and validated {len(payloads)} contracts")
