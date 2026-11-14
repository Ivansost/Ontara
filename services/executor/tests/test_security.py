import pytest
from ontara_executor.security import NetworkScope, TargetPolicy, UnsafeTarget, redact_url


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


def test_read_only_context_blocks_page_script_writes_to_allowlisted_host():
    scope = NetworkScope(TargetPolicy("https://portals.example.invalid", {"portals.example.invalid"}))
    url = "https://portals.example.invalid/portals/roads/tickets"
    assert scope.permits("GET", url)
    assert scope.permits("HEAD", url)
    for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT"):
        assert not scope.permits(method, url, content_type="application/x-www-form-urlencoded", post_data="location=unapproved")


def test_submit_scope_allows_only_one_exact_validated_form_post():
    scope = NetworkScope(TargetPolicy("https://portals.example.invalid", {"portals.example.invalid"}))
    url = "https://portals.example.invalid/portals/roads/tickets"
    scope.arm_form_post(url, {"clientReference": "approved-ref", "location": "Approved road", "optional": ""})
    good = "clientReference=approved-ref&location=Approved+road&optional="
    assert not scope.permits("POST", url + "/other", content_type="application/x-www-form-urlencoded", post_data=good)
    assert not scope.permits("POST", url, content_type="application/json", post_data=good)
    assert not scope.permits("POST", url, content_type="application/x-www-form-urlencoded", post_data=good.replace("Approved+road", "unapproved"))
    assert not scope.permits("POST", url, content_type="application/x-www-form-urlencoded", post_data=good + "&location=unapproved")
    assert scope.permits("POST", url, content_type="application/x-www-form-urlencoded; charset=UTF-8", post_data=good)
    assert not scope.permits("POST", url, content_type="application/x-www-form-urlencoded", post_data=good)
