"""ElevenLabs control plane. Workspace credentials never leave this server."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from ..service import DomainError

CONVERSATION_ID = re.compile(r"^conv_[A-Za-z0-9_-]{6,100}$")


@dataclass(frozen=True)
class VoiceSettings:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    agent_id: str = ""
    minimum_credits: int = 1500
    daily_sessions: int = 12
    owner_daily_sessions: int = 3

    @classmethod
    def load(cls) -> "VoiceSettings":
        return cls(enabled=os.environ.get("ONTARA_VOICE_ENABLED", "false").lower() == "true",
                   api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
                   agent_id=os.environ.get("ELEVENLABS_AGENT_ID", ""))

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.api_key and self.agent_id)


class ElevenLabsGateway:
    def __init__(self, settings: VoiceSettings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _get(self, path: str, **params) -> dict:
        try:
            with httpx.Client(base_url="https://api.elevenlabs.io", timeout=20,
                              follow_redirects=False, transport=self.transport) as client:
                result = client.get(path, params=params, headers={"xi-api-key": self.settings.api_key})
                result.raise_for_status()
                data = result.json()
        except (httpx.HTTPError, ValueError):
            # Exception text may contain the secret-bearing request or signed URL.
            raise DomainError(503, "Voice is temporarily unavailable. Continue with the written form.") from None
        if not isinstance(data, dict):
            raise DomainError(503, "The voice service returned an unexpected response. Continue with the form.")
        return data

    def signed_session(self) -> dict:
        agent = self._get("/v1/convai/agents/" + quote(self.settings.agent_id, safe=""))
        platform = agent.get("platform_settings") or {}
        duration = (agent.get("conversation_config") or {}).get("conversation", {}).get("max_duration_seconds", 0)
        if (platform.get("auth", {}).get("enable_auth") is not True
                or platform.get("privacy", {}).get("record_voice") is not False
                or not isinstance(duration, int) or not 1 <= duration <= 180):
            raise DomainError(503, "Voice privacy or session limits need configuration. Continue with the written form.")
        subscription = self._get("/v1/user/subscription")
        used, limit = subscription.get("character_count"), subscription.get("character_limit")
        if (not isinstance(used, int) or not isinstance(limit, int)
                or limit - used < self.settings.minimum_credits):
            raise DomainError(503, "The demo voice allowance is low. Continue with the written form.")
        result = self._get("/v1/convai/conversation/get-signed-url", agent_id=self.settings.agent_id,
                           include_conversation_id="true")
        signed_url = result.get("signed_url", "")
        if not isinstance(signed_url, str):
            raise DomainError(503, "A private voice session could not be prepared.")
        parsed = urlsplit(signed_url)
        conversation_id = result.get("conversation_id") or parse_qs(parsed.query).get("conversation_id", [""])[0]
        if (parsed.scheme != "wss" or parsed.hostname != "api.elevenlabs.io"
                or parsed.path != "/v1/convai/conversation" or parsed.username or parsed.password
                or not isinstance(conversation_id, str) or not CONVERSATION_ID.fullmatch(conversation_id)):
            raise DomainError(503, "A scoped voice session could not be verified. Continue with the form.")
        return {"signedUrl": signed_url, "conversationId": conversation_id}

    def conversation(self, conversation_id: str) -> dict:
        if not CONVERSATION_ID.fullmatch(conversation_id):
            raise DomainError(503, "The voice conversation reference is invalid.")
        result = self._get("/v1/convai/conversations/" + quote(conversation_id, safe=""))
        if result.get("agent_id") != self.settings.agent_id or result.get("conversation_id") != conversation_id:
            raise DomainError(503, "The voice conversation does not match this intake session.")
        return result
