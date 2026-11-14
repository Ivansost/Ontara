"""Guard the authenticated hosted helper against sends without a real saved receipt."""
import importlib.util
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location("ontara_hosted_mail_probe", Path(__file__).resolve().parents[4] / "scripts/mail/trigger_followup.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("origin", ["http://example.com", "https://example.com", "https://bad.onrender.com.evil.test",
                                    "https://token@demo.onrender.com", "https://demo.onrender.com/path",
                                    "https://demo.onrender.com?token=value"])
def test_private_token_is_not_sent_to_unapproved_origin(origin):
    with pytest.raises(ValueError):
        probe.validate_origin(origin)


def test_render_https_and_loopback_origins_are_supported():
    assert probe.validate_origin("https://ontara-api-demo.onrender.com/") == "https://ontara-api-demo.onrender.com"
    assert probe.validate_origin("http://127.0.0.1:8001") == "http://127.0.0.1:8001"


@pytest.mark.parametrize("mode", ["no_receipt", "live_route", "cancelled", "unverified_operation"])
def test_missing_receipt_or_demo_scope_cannot_reach_a_post(mode):
    calls = []
    case = {"id": "case_test", "route": {"demo": True, "id": "halton-roads-demo"},
            "receipt": {"ticketId": "SYNTHETIC-TICKET"}, "currentOperationId": "op_test"}
    if mode == "no_receipt":
        case["receipt"] = None
    elif mode == "live_route":
        case["route"]["demo"] = False
    elif mode == "cancelled":
        case["cancelledAt"] = "2026-11-14T12:00:00Z"
    def handle(request):
        calls.append(request.method)
        assert request.method == "GET"
        if "/cases/" in request.url.path:
            return httpx.Response(200, json=case)
        return httpx.Response(200, json={"caseId": "case_test", "state": "dispatch_started",
                                        "receipt": {"ticketId": "SYNTHETIC-TICKET"}})
    with httpx.Client(base_url="https://demo.onrender.com", transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError):
            probe.verify_existing_case(client, "case_test")
    assert "POST" not in calls


def test_saved_matching_verified_receipt_passes_without_creating_anything():
    calls = []
    def handle(request):
        calls.append(request.method)
        assert request.headers["Authorization"] == "Bearer test-token"
        if "/cases/" in request.url.path:
            return httpx.Response(200, json={"route": {"demo": True, "id": "halton-roads-demo"},
                                            "receipt": {"ticketId": "SYNTHETIC-TICKET"}, "currentOperationId": "op_test"})
        return httpx.Response(200, json={"caseId": "case_test", "state": "receipt_verified",
                                        "receipt": {"ticketId": "SYNTHETIC-TICKET"}})
    with httpx.Client(base_url="https://demo.onrender.com", headers={"Authorization": "Bearer test-token"},
                      transport=httpx.MockTransport(handle)) as client:
        probe.verify_existing_case(client, "case_test")
    assert calls == ["GET", "GET"]
