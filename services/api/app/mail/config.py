"""Private, explicit configuration for the three controlled demo mail roles."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path
from typing import Mapping


def read_env_file(path: str | Path) -> dict[str, str]:
    """Read dotenv-style assignments as data; never execute a credential file."""
    result: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def address(value: str) -> str:
    return parseaddr(value)[1].lower().strip()


@dataclass(frozen=True)
class MailSettings:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    ontara_inbox_id: str = ""
    authority_inbox_id: str = ""
    resident_inbox_id: str = ""
    allowed_inbox_ids: frozenset[str] = frozenset()
    poll_seconds: int = 8
    lease_seconds: int = 90
    max_attachment_bytes: int = 8 * 1024 * 1024
    daily_send_budget: int = 60
    catchup_overlap_seconds: int = 300

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> MailSettings:
        values = os.environ if values is None else values
        settings = cls(
            enabled=values.get("ONTARA_MAIL_ENABLED", "false").lower() in {"1", "true", "yes"},
            api_key=values.get("AGENTMAIL_API_KEY", ""),
            ontara_inbox_id=values.get("ONTARA_MAIL_INBOX_ID", "").lower(),
            authority_inbox_id=values.get("ONTARA_MAIL_AUTHORITY_INBOX_ID", "").lower(),
            resident_inbox_id=values.get("ONTARA_MAIL_RESIDENT_INBOX_ID", "").lower(),
            allowed_inbox_ids=frozenset(
                item.strip().lower()
                for item in values.get("ONTARA_MAIL_ALLOWED_INBOX_IDS", "").split(",")
                if item.strip()
            ),
            poll_seconds=max(3, int(values.get("ONTARA_MAIL_POLL_SECONDS", "8"))),
            daily_send_budget=min(90, max(1, int(values.get("ONTARA_MAIL_DAILY_SEND_BUDGET", "60")))),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.enabled:
            return
        roles = {self.ontara_inbox_id, self.authority_inbox_id, self.resident_inbox_id}
        if not self.api_key or len(roles) != 3 or not all(roles):
            raise ValueError("AgentMail requires a key and three distinct controlled inbox roles")
        if roles != set(self.allowed_inbox_ids):
            raise ValueError("Mail allowlist must contain exactly the three controlled role inboxes")
        if any(address(value) != value or not value.endswith("@agentmail.to") for value in roles):
            raise ValueError("This demo only supports explicit controlled agentmail.to inboxes")

    def require_participants(self, sender: str, recipients: list[str]) -> None:
        if sender not in self.allowed_inbox_ids or not recipients:
            raise ValueError("Unconfigured mail sender or recipient")
        if any(recipient not in self.allowed_inbox_ids for recipient in recipients):
            raise ValueError("Sending outside controlled demo inboxes is forbidden")

    @property
    def role_inboxes(self) -> tuple[str, str, str]:
        return self.ontara_inbox_id, self.authority_inbox_id, self.resident_inbox_id
