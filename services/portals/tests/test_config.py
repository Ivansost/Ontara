from ontara_portals.config import Settings


def test_render_external_url_fallback_and_explicit_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ONTARA_MONGODB_ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setenv("DEMO_PORTAL_MONGODB_URI", "mongodb://unused")
    monkeypatch.setenv("DEMO_PORTAL_ADMIN_TOKEN", "a" * 40)
    monkeypatch.delenv("PORTALS_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://ontara-portals-actual-suffix.onrender.com")
    assert Settings.from_environment().public_base_url == "https://ontara-portals-actual-suffix.onrender.com"
    monkeypatch.setenv("PORTALS_PUBLIC_BASE_URL", "https://custom.example.test/")
    assert Settings.from_environment().public_base_url == "https://custom.example.test"
