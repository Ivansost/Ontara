from __future__ import annotations

import hashlib
import json
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class UnsafeTarget(ValueError):
    pass


def stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, "[redacted]" if any(t in k.lower() for t in ("token", "secret", "key", "auth")) else v) for k, v in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class TargetPolicy:
    def __init__(self, base_url: str | None = None, allowed_hosts: set[str] | None = None):
        self.base_url = (base_url or os.environ.get("PORTALS_BASE_URL", "")).rstrip("/")
        base = urlsplit(self.base_url)
        if not base.hostname or base.username or base.password:
            raise UnsafeTarget("PORTALS_BASE_URL must be a credential-free absolute URL")
        self.allow_http = os.environ.get("ONTARA_ALLOW_LOCAL_HTTP") == "1"
        self.allowed_hosts = allowed_hosts or {h.strip().lower() for h in os.environ.get("ALLOWED_PORTAL_HOSTS", base.hostname).split(",") if h.strip()}
        if base.hostname.lower() not in self.allowed_hosts:
            raise UnsafeTarget("Portal base host is not allowlisted")
        self.origin = (base.scheme, base.hostname.lower(), base.port)
        self.validate(self.base_url + "/portals/roads/new")

    def validate(self, url: str, *, portal_id: str | None = None) -> str:
        p = urlsplit(url)
        if p.username or p.password or p.fragment or not p.hostname:
            raise UnsafeTarget("Invalid browser destination")
        if (p.scheme, p.hostname.lower(), p.port) != self.origin:
            raise UnsafeTarget("Browser destination must use the configured portal origin")
        if p.scheme != "https" and not (self.allow_http and p.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise UnsafeTarget("Browser destinations require HTTPS")
        if p.hostname.lower() not in self.allowed_hosts:
            raise UnsafeTarget("Browser host is not allowlisted")
        if portal_id and not p.path.startswith("/portals/" + portal_id + "/"):
            raise UnsafeTarget("Browser destination does not match the approved portal")
        return url
