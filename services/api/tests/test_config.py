import pytest

from app.config import resolve_dispatch_url


def test_dispatch_origin_derives_endpoint_and_explicit_url_wins():
    assert resolve_dispatch_url("", "https://executor.example/") == "https://executor.example/internal/v1/run"
    assert resolve_dispatch_url(" https://explicit.example/custom-run ", "https://executor.example") == "https://explicit.example/custom-run"
    assert resolve_dispatch_url("", "http://127.0.0.1:8003") == "http://127.0.0.1:8003/internal/v1/run"


def test_blank_dispatch_never_builds_a_relative_endpoint():
    assert resolve_dispatch_url("", "") == ""
    assert resolve_dispatch_url(" ", " ") == ""


@pytest.mark.parametrize("explicit,base", [("/internal/v1/run", ""), ("", "executor.example"), ("", "https://executor.example/path"), ("", "https://executor.example?key=value")])
def test_invalid_dispatch_target_is_rejected(explicit, base):
    with pytest.raises(ValueError):
        resolve_dispatch_url(explicit, base)
