"""Opt-in actual-browser security regression; no Atlas or provider calls."""
import asyncio
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
from urllib.parse import parse_qs, urlsplit

import pytest
from ontara_executor.browser import BrowserTools
from ontara_executor.contracts import BrowserContext, SubmitRequest
from ontara_executor.security import TargetPolicy

pytestmark = pytest.mark.skipif(os.environ.get("ONTARA_RUN_BROWSER_TESTS") != "1", reason="Opt-in matching-browser integration test")


@pytest.fixture
def receiver():
    class Handler(BaseHTTPRequestHandler):
        posts = []
        def log_message(self, *args):
            pass
        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            hidden = "".join(f'<input type="hidden" name="{name}" value="{query.get(name, ["test"])[0]}">' for name in ("runId", "clientReference", "payloadDigest"))
            body = ("<html><head><title>Untrusted form</title></head><body>"
                    "<script>fetch('/portals/roads/tickets',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'location=unapproved-script-write'}).catch(()=>{}).finally(()=>window.attemptComplete=true)</script>"
                    f'<form method="post" action="/portals/roads/tickets">{hidden}<input type="hidden" name="formVersion" value="1">'
                    '<label for="location">Location</label><input id="location" name="location" required>'
                    '<label for="description">Description</label><textarea id="description" name="description" required></textarea>'
                    '<button type="submit">Submit</button></form></body></html>').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            values = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode(), keep_blank_values=True)
            Handler.posts.append(values)
            origin = f"http://127.0.0.1:{self.server.server_port}"
            receipt = {"runId": values.get("runId", [""])[0], "clientReference": values.get("clientReference", [""])[0], "payloadDigest": values.get("payloadDigest", [""])[0], "portalId": "roads", "action": "create", "ticketId": "test-ticket", "receiptId": "test-receipt", "acceptedAt": datetime.now(timezone.utc).isoformat(), "receiptUrl": origin + "/portals/roads/receipt", "ticketUrl": origin + "/portals/roads/tickets/test-ticket", "updateUrl": origin + "/portals/roads/tickets/test-ticket/update?accessToken=test-only"}
            body = ('<script id="ontara-receipt" type="application/json">' + json.dumps(receipt) + '</script>').encode()
            self.send_response(201)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", Handler.posts
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


async def test_inspection_blocks_actual_page_script_post(receiver, monkeypatch):
    origin, posts = receiver
    monkeypatch.setenv("ONTARA_ALLOW_LOCAL_HTTP", "1")
    tools = BrowserTools(TargetPolicy(origin, {"127.0.0.1"}))
    try:
        async with tools.page() as page:
            await page.goto(origin + "/untrusted")
            await page.wait_for_function("window.attemptComplete === true")
        assert posts == []
    finally:
        await tools.close()


async def test_submit_permits_only_validated_native_form_post(receiver, monkeypatch):
    origin, posts = receiver
    monkeypatch.setenv("ONTARA_ALLOW_LOCAL_HTTP", "1")
    tools = BrowserTools(TargetPolicy(origin, {"127.0.0.1"}))
    context = BrowserContext(operation_id="test-operation", case_id="test-case", run_id="test-run", attempt_id="test-attempt", portal_id="roads", client_reference="test-operation", payload_digest="a" * 64, action="create")
    try:
        observation = (await tools.inspect(context)).observation
        assert posts == []
        result = await tools.submit(SubmitRequest(**context.model_dump(), form_fingerprint=observation.fingerprint, values={"location": "Approved synthetic road", "description": "Approved synthetic description"}))
        assert result.accepted and result.receipt["receiptId"] == "test-receipt"
        assert len(posts) == 1
        assert posts[0]["location"] == ["Approved synthetic road"]
        assert posts[0]["clientReference"] == ["test-operation"]
    finally:
        await tools.close()
