from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    admin_token: str
    receipt_secret: str
    public_base_url: str = "http://127.0.0.1:8002"
    database_name: str = "ontara_demo"

    @classmethod
    def from_environment(cls) -> "Settings":
        # dotenv_values parses data without executing shell code or exporting secrets.
        path = Path(os.environ.get("ONTARA_MONGODB_ENV_FILE", "~/.config/ontara/mongodb.env")).expanduser()
        private = dotenv_values(path) if path.is_file() else {}
        uri = os.environ.get("DEMO_PORTAL_MONGODB_URI") or private.get("DEMO_PORTAL_MONGODB_URI") or ""
        admin_token = os.environ.get("DEMO_PORTAL_ADMIN_TOKEN", "")
        secret = os.environ.get("DEMO_PORTAL_RECEIPT_SECRET") or admin_token
        base = os.environ.get("PORTALS_PUBLIC_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
        parts = urlsplit(base)
        if not uri:
            raise RuntimeError("DEMO_PORTAL_MONGODB_URI is required; credential values are never logged")
        if len(admin_token) < 32 or len(secret) < 32:
            raise RuntimeError("Set DEMO_PORTAL_ADMIN_TOKEN to at least 32 random characters")
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.path not in {"", "/"} or parts.query or parts.fragment or parts.username:
            raise RuntimeError("PORTALS_PUBLIC_BASE_URL must be an http(s) origin without a path, query or credentials")
        if parts.scheme != "https" and parts.hostname not in {"localhost", "127.0.0.1", "testserver"}:
            raise RuntimeError("A public portal URL must use HTTPS")
        return cls(uri, admin_token, secret, base)
