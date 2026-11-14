from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = ""
    database_name: str = "ontara"
    internal_token: str = ""
    session_secret: str = ""
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    portal_base_url: str = "http://localhost:8001"
    dispatch_url: str = ""
    max_artifact_bytes: int = 20 * 1024 * 1024

    @classmethod
    def load(cls, env_file: str | None = None) -> Settings:
        # Parse dotenv as data: never source a credential-bearing file as shell code.
        path = Path(env_file or os.environ.get("ONTARA_ENV_FILE", "~/.config/ontara/mongodb.env")).expanduser()
        private = dotenv_values(path) if path.is_file() else {}
        def value(key: str, default: str = "") -> str:
            return os.environ.get(key, private.get(key) or default)
        return cls(
            mongodb_uri=value("MONGODB_URI"),
            database_name=value("MONGODB_DATABASE", "ontara"),
            internal_token=value("ONTARA_INTERNAL_TOKEN"),
            session_secret=value("ONTARA_SESSION_SECRET"),
            cookie_secure=value("SESSION_COOKIE_SECURE", "true").lower() == "true",
            allowed_origins=tuple(x.strip() for x in value("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if x.strip()),
            portal_base_url=value("DEMO_PORTAL_BASE_URL", "http://localhost:8001").rstrip("/"),
            dispatch_url=value("ONTARA_AGENT_DISPATCH_URL"),
        )
