import pytest
from ontara_executor.security import TargetPolicy, UnsafeTarget, redact_url


def test_targets_cannot_redirect_to_another_host_or_portal(monkeypatch):
    monkeypatch.delenv("ONTARA_ALLOW_LOCAL_HTTP", raising=False)
    policy = TargetPolicy("https://portals.example.invalid", {"portals.example.invalid"})
    for url in ("https://attacker.example.invalid/portals/roads/new", "https://user:password@portals.example.invalid/portals/roads/new", "http://portals.example.invalid/portals/roads/new", "https://portals.example.invalid:444/portals/roads/new", "https://portals.example.invalid/portals/graffiti/new"):
        with pytest.raises(UnsafeTarget):
            policy.validate(url, portal_id="roads")


def test_capability_urls_are_redacted():
    value = redact_url("https://demo.invalid/portals/roads/tickets/x/update?runId=demo&accessToken=secret-capability")
    assert "secret-capability" not in value
    assert "runId=demo" in value
