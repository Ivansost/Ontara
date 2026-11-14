"""AgentMail HTTP boundary. No automatic retry of any external send."""

from __future__ import annotations

from typing import Any, Iterator
from urllib.parse import quote, urlparse

import httpx

API_ROOT = "https://api.agentmail.to/v0"


class ProviderFailure(RuntimeError):
    def __init__(self, code: str, *, ambiguous: bool = False, retryable: bool = False):
        super().__init__(code)
        self.code, self.ambiguous, self.retryable = code, ambiguous, retryable


class AgentMailProvider:
    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=httpx.Timeout(25), follow_redirects=False)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, API_ROOT + path, headers=self._headers, **kwargs)
        except httpx.HTTPError:
            # A timeout after request transmission can still have sent an email.
            raise ProviderFailure("provider_transport_error", ambiguous=method != "GET", retryable=method == "GET") from None
        if response.status_code >= 400:
            raise ProviderFailure(
                f"provider_http_{response.status_code}",
                ambiguous=method != "GET" and (response.status_code >= 500 or response.status_code == 408),
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        try:
            return response.json()
        except ValueError:
            raise ProviderFailure("provider_invalid_response", ambiguous=method != "GET") from None

    def organization(self) -> dict[str, Any]:
        return self._request("GET", "/organizations")

    def list_inboxes(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": 100}
        while True:
            page = self._request("GET", "/inboxes", params=params)
            result.extend(page.get("inboxes", []))
            if not page.get("next_page_token"):
                return result
            params["page_token"] = page["next_page_token"]

    def messages(self, inbox_id: str, *, after: str | None = None, labels: list[str] | None = None) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 100}
        if after:
            # The live API currently accepts UTC Z datetimes, rejecting +00:00.
            params["after"] = after.replace("+00:00", "Z")
        if labels:
            params["labels"] = labels
        # Pagination is exhaustive; never advance a durable cursor after a partial page read.
        seen: set[str] = set()
        while True:
            page = self._request("GET", f"/inboxes/{quote(inbox_id, safe='')}/messages", params=params)
            yield from page.get("messages", [])
            token = page.get("next_page_token")
            if not token:
                return
            if token in seen:
                raise ProviderFailure("provider_repeated_page_token")
            seen.add(token)
            params["page_token"] = token

    def get_message(self, inbox_id: str, message_id: str) -> dict[str, Any]:
        return self._request("GET", f"/inboxes/{quote(inbox_id, safe='')}/messages/{quote(message_id, safe='')}")

    def send(self, item: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "to": item["recipients"], "subject": item["subject"], "text": item["text"],
            "labels": ["ontara-demo", item["providerLabel"]],
            "headers": {"X-Ontara-Correlation": item["correlationToken"]},
        }
        if item.get("inReplyTo"):
            payload["headers"]["In-Reply-To"] = item["inReplyTo"]
            payload["headers"]["References"] = item["inReplyTo"]
        result = self._request("POST", f"/inboxes/{quote(item['senderInboxId'], safe='')}/messages/send", json=payload)
        if not result.get("message_id") or not result.get("thread_id"):
            raise ProviderFailure("provider_missing_send_ids", ambiguous=True)
        return result

    def get_attachment(self, inbox_id: str, message_id: str, attachment_id: str, max_bytes: int) -> tuple[bytes, dict[str, Any]]:
        metadata = self._request(
            "GET", f"/inboxes/{quote(inbox_id, safe='')}/messages/{quote(message_id, safe='')}/attachments/{quote(attachment_id, safe='')}"
        )
        url = metadata.get("download_url", "")
        parsed = urlparse(url)
        # Only a provider-issued HTTPS object-store URL is followed; email URLs never reach this method.
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ProviderFailure("unsafe_provider_attachment_url")
        if not (parsed.hostname.endswith(".amazonaws.com") or parsed.hostname.endswith(".agentmail.to") or parsed.hostname.endswith(".cloudflarestorage.com")):
            raise ProviderFailure("unrecognized_provider_attachment_host")
        content = bytearray()
        try:
            # This client request intentionally has no AgentMail Authorization header.
            with self.client.stream("GET", url, follow_redirects=False) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ProviderFailure("attachment_too_large")
        except httpx.HTTPError:
            raise ProviderFailure("attachment_download_failed", retryable=True) from None
        return bytes(content), metadata
