from __future__ import annotations

import sys
from pathlib import Path

import mongomock
import pytest
from mongomock.gridfs import enable_gridfs_integration

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.service import CaseService
from app.storage import ArtifactStore, Store


@pytest.fixture
def store():
    enable_gridfs_integration()
    db = mongomock.MongoClient(tz_aware=True).ontara
    current = Store(db, transactions=False)
    current.ensure_indexes()
    return current


@pytest.fixture
def settings():
    return Settings(internal_token="test-internal-token", cookie_secure=False)


@pytest.fixture
def cases(store, settings, monkeypatch):
    result = CaseService(store, settings)
    # These ledger tests inject a known source decision; native search has separate live checks.
    monkeypatch.setattr(result, "_knowledge", lambda *_: {"status": "ready", "selected": {
        "id": "unit-test-procedure", "sourceVersion": "1", "title": "Synthetic unit test source decision", "authorityId": "halton-region",
        "verificationStatus": "verified", "integrationStatus": "research_only", "sourceRefs": [
            {"id": "unit-test-source", "sourceVersion": "1", "title": "Synthetic unit test source", "url": "https://test.example/fixture"}]},
        "evidence": {"nativeQuery": False, "testFixture": True}})
    return result


@pytest.fixture
def artifacts(store):
    result = ArtifactStore(store.db)
    # mongomock's dynamic client.options.timeout is not a real numeric driver option.
    result.bucket._timeout = None
    return result
