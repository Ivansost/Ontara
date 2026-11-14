import json

import httpx
import pytest

from app.mail.provider import AgentMailProvider, ProviderFailure


def item():
    return {"senderInboxId": "authority@agentmail.to", "recipients": ["ontara@agentmail.to"],
            "subject": "Controlled demo", "text": "Test message", "providerLabel": "ontara-token",
            "correlationToken": "token", "inReplyTo": "<prior@agentmail.to>"}


def test_send_uses_explicit_recipients_and_correlation_headers():
    calls = []
    def handle(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["to"] == ["ontara@agentmail.to"]
        assert body["headers"]["X-Ontara-Correlation"] == "token"
        assert body["headers"]["In-Reply-To"] == "<prior@agentmail.to>"
        assert request.headers["Authorization"] == "Bearer test-private-key"
        return httpx.Response(200, json={"message_id": "<message>", "thread_id": "thread"})
    provider = AgentMailProvider("test-private-key", httpx.Client(transport=httpx.MockTransport(handle)))
    assert provider.send(item())["message_id"] == "<message>"
    assert len(calls) == 1


@pytest.mark.parametrize("status,ambiguous", [(403, False), (429, False), (500, True), (408, True)])
def test_provider_send_error_never_auto_retries_or_discloses_response(status, ambiguous):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "secret-private-provider-response"})
    provider = AgentMailProvider("test-key", httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderFailure) as caught:
        provider.send(item())
    assert caught.value.ambiguous == ambiguous
    assert "secret-private" not in str(caught.value)
    assert len(calls) == 1


def test_full_pagination_and_repeated_token_guard():
    count = 0
    def handle(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"messages": [{"message_id": str(count)}], "next_page_token": "same"})
    provider = AgentMailProvider("test", httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderFailure, match="repeated_page"):
        list(provider.messages("ontara@agentmail.to"))
    assert count == 2


def test_date_filter_uses_live_api_utc_z_format():
    def handle(request):
        assert request.url.params["after"] == "2026-11-14T00:00:00Z"
        return httpx.Response(200, json={"messages": []})
    provider = AgentMailProvider("test", httpx.Client(transport=httpx.MockTransport(handle)))
    assert list(provider.messages("ontara@agentmail.to", after="2026-11-14T00:00:00+00:00")) == []


def test_attachment_download_does_not_forward_bearer_key():
    def handle(request):
        if request.url.host == "api.agentmail.to":
            assert "authorization" in request.headers
            return httpx.Response(200, json={"download_url": "https://test.s3.amazonaws.com/file?signature=example"})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"private attachment bytes")
    provider = AgentMailProvider("test-key", httpx.Client(transport=httpx.MockTransport(handle)))
    data, _ = provider.get_attachment("ontara@agentmail.to", "<message>", "attachment", 100)
    assert data == b"private attachment bytes"


def test_attachment_url_from_email_cannot_target_private_network():
    def handle(request):
        return httpx.Response(200, json={"download_url": "http://127.0.0.1/private"})
    provider = AgentMailProvider("test-key", httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderFailure, match="unsafe"):
        provider.get_attachment("ontara@agentmail.to", "<message>", "attachment", 100)
