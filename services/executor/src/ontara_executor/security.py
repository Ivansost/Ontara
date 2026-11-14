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


class NetworkScope:
    """Read-only by default; one exact form POST can be armed after validation."""

    def __init__(self, policy: TargetPolicy):
        self.policy = policy
        self._post_url: str | None = None
        self._post_values: dict[str, str] | None = None
        self._used = False

    def arm_form_post(self, url: str, values: dict[str, str]):
        self.policy.validate(url)
        if self._post_url is not None or self._used or not values:
            raise ValueError("A browser context can authorize one form POST only")
        self._post_url, self._post_values = url, dict(values)

    def permits(self, method: str, url: str, *, content_type: str = "", post_data: str | None = None) -> bool:
        try:
            self.policy.validate(url)
        except UnsafeTarget:
            return False
        if method in {"GET", "HEAD"}:
            return True
        if method != "POST" or self._used or url != self._post_url or self._post_values is None:
            return False
        if content_type.split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded" or post_data is None:
            return False
        try:
            pairs = parse_qsl(post_data, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return False
        if len(pairs) != len(dict(pairs)) or dict(pairs) != self._post_values:
            return False
        self._used = True
        return True
