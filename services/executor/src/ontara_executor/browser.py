from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Browser, BrowserContext as PlaywrightContext, Page, async_playwright
from .contracts import BrowserContext, BrowserResult, FieldObservation, FormObservation, SubmitRequest
from .security import NetworkScope, TargetPolicy, normalized_form_values, redact_url, stable_hash


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrowserTools:
    """One Chromium task; every network request remains on the configured origin."""

    def __init__(self, policy: TargetPolicy):
        self.policy = policy
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        channel = os.environ.get("ONTARA_LOCAL_BROWSER_CHANNEL")
        if channel and os.environ.get("ONTARA_ALLOW_LOCAL_HTTP") != "1":
            raise ValueError("A local installed browser channel is restricted to explicit development tests")
        self._browser = await self._playwright.chromium.launch(headless=True, channel=channel, args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"])

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @asynccontextmanager
    async def page(self, write_scope: NetworkScope | None = None):
        async with self._lock:
            if not self._browser or not self._browser.is_connected():
                await self.start()
            context: PlaywrightContext = await self._browser.new_context(service_workers="block", accept_downloads=False)
            scope = write_scope or NetworkScope(self.policy)
            async def route_request(route):
                request = route.request
                if not scope.permits(request.method, request.url, content_type=request.headers.get("content-type", ""), post_data=request.post_data):
                    await route.abort("blockedbyclient")
                else:
                    await route.continue_()
            await context.route("**/*", route_request)
            async def block_socket(socket):
                await socket.close(code=1008, reason="Browser tools do not authorize WebSocket connections")
            await context.route_web_socket("**/*", block_socket)
            page = await context.new_page()
            page.set_default_timeout(20000)
            try:
                yield page
            finally:
                await context.close()

    def url(self, ctx: BrowserContext, *, lookup: bool = False) -> str:
        if ctx.client_reference != ctx.operation_id:
            raise ValueError("Client reference must be the frozen logical operation ID")
        if lookup:
            url = f"{self.policy.base_url}/portals/{ctx.portal_id}/lookup"
        elif ctx.action == "create":
            url = f"{self.policy.base_url}/portals/{ctx.portal_id}/new"
        else:
            if not ctx.update_url or not ctx.ticket_id:
                raise ValueError("An update requires the original verified ticket and authorized update URL")
            url = self.policy.validate(ctx.update_url, portal_id=ctx.portal_id)
            if f"/tickets/{ctx.ticket_id}/update" != urlsplit(url).path.removeprefix(f"/portals/{ctx.portal_id}"):
                raise ValueError("Update URL does not match the original verified ticket")
        p = urlsplit(url)
        q = {k: v for k, v in parse_qsl(p.query) if k not in {"runId", "clientReference", "payloadDigest"}}
        q.update(runId=ctx.run_id, clientReference=ctx.client_reference, payloadDigest=ctx.payload_digest)
        return self.policy.validate(urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), "")), portal_id=ctx.portal_id)

    async def observe(self, page: Page, ctx: BrowserContext) -> FormObservation:
        self.policy.validate(page.url, portal_id=ctx.portal_id)
        data = await page.locator("form").first.evaluate("""form => ({
          actionUrl: form.action, method: form.method.toUpperCase(),
          fields: Array.from(form.elements).filter(e => e.name && !['submit','button'].includes(e.type)).map(e => ({
            name: e.name, label: Array.from(e.labels || []).map(l => l.textContent.trim()).join(' ') || e.getAttribute('aria-label') || e.name,
            type: e.tagName === 'TEXTAREA' ? 'textarea' : e.type,
            required: !!e.required, disabled: !!e.disabled,
            options: e.tagName === 'SELECT' ? Array.from(e.options).filter(o => !o.disabled).map(o => o.value) : []
          })), formVersion: (form.elements.namedItem('formVersion') || {}).value || 'unknown'
        })""")
        self.policy.validate(data["actionUrl"], portal_id=ctx.portal_id)
        expected_action = f"/portals/{ctx.portal_id}/tickets" + (f"/{ctx.ticket_id}/update" if ctx.action == "update" else "")
        if urlsplit(data["actionUrl"]).path != expected_action:
            raise ValueError("Receiving form action does not match the approved operation")
        if data["method"] != "POST":
            raise ValueError("Only a receiving POST form is supported")
        names = [f["name"] for f in data["fields"]]
        if len(names) != len(set(names)):
            raise ValueError("Ambiguous repeated form field names require assistance")
        fingerprint = stable_hash({k: data[k] for k in ("method", "formVersion", "fields")} | {"actionPath": urlsplit(data["actionUrl"]).path})
        return FormObservation(url=redact_url(page.url), action_url=redact_url(data["actionUrl"]), method=data["method"], form_version=data["formVersion"], fingerprint=fingerprint, fields=[FieldObservation(**f) for f in data["fields"]], observed_at=now())

    async def inspect(self, ctx: BrowserContext) -> BrowserResult:
        async with self.page() as page:
            response = await page.goto(self.url(ctx), wait_until="domcontentloaded")
            if not response or response.status >= 400:
                return BrowserResult(status="rejected", response_status=response.status if response else None)
            return BrowserResult(status="observed", observation=await self.observe(page, ctx), evidence={"tool": "playwright.inspect", "observedAt": now()})

    async def _receipt(self, page: Page, ctx: BrowserContext) -> dict:
        self.policy.validate(page.url, portal_id=ctx.portal_id)
        receipt = json.loads(await page.locator("script#ontara-receipt").text_content())
        expected = {"runId": ctx.run_id, "portalId": ctx.portal_id, "clientReference": ctx.client_reference, "payloadDigest": ctx.payload_digest, "action": ctx.action}
        if any(receipt.get(k) != value for k, value in expected.items()):
            raise ValueError("Receiving receipt does not match the frozen operation")
        if ctx.action == "update" and receipt.get("ticketId") != ctx.ticket_id:
            raise ValueError("Receiving acknowledgement refers to a different ticket")
        for k in ("receiptUrl", "ticketUrl", "updateUrl"):
            if receipt.get(k):
                self.policy.validate(receipt[k], portal_id=ctx.portal_id)
        if not receipt.get("receiptId") or not receipt.get("ticketId") or not receipt.get("acceptedAt"):
            raise ValueError("Receiving receipt is incomplete")
        return receipt

    async def reconcile(self, ctx: BrowserContext) -> BrowserResult:
        async with self.page() as page:
            response = await page.goto(self.url(ctx, lookup=True), wait_until="domcontentloaded")
            status = response.status if response else None
            if status == 404:
                # A missing lookup is not proof an ambiguous create was unapplied.
                return BrowserResult(status="not_found", response_status=status, evidence={"tool": "playwright.lookup", "checkedAt": now()})
            if status is None or status >= 400:
                return BrowserResult(status="unknown", response_status=status)
            receipt = await self._receipt(page, ctx)
            return BrowserResult(status="accepted", accepted=True, receipt=receipt, response_status=status, evidence={"tool": "playwright.lookup", "checkedAt": now(), "receiptId": receipt["receiptId"], "ticketId": receipt["ticketId"]})

    async def submit(self, request: SubmitRequest) -> BrowserResult:
        write_scope = NetworkScope(self.policy)
        async with self.page(write_scope) as page:
            await page.goto(self.url(request), wait_until="domcontentloaded")
            observation = await self.observe(page, request)
            if observation.fingerprint != request.form_fingerprint:
                return BrowserResult(status="rejected", observation=observation, evidence={"reason": "form_changed_before_dispatch"})
            controls = {f.name: f for f in observation.fields}
            hidden = {"runId": request.run_id, "clientReference": request.client_reference, "payloadDigest": request.payload_digest, "formVersion": observation.form_version}
            if request.action == "update":
                token = dict(parse_qsl(urlsplit(request.update_url).query)).get("accessToken")
                if not token:
                    raise ValueError("The approved update capability is missing")
                hidden["accessToken"] = token
            for name, value in hidden.items():
                if name not in controls or controls[name].type != "hidden" or controls[name].disabled:
                    raise ValueError("Receiving form is missing operation binding")
                existing = await page.locator("form").first.locator(f'[name="{name}"]').input_value()
                if existing != value:
                    raise ValueError("Receiving form operation binding changed")
            for name, value in request.values.items():
                field = controls.get(name)
                if not field or field.type == "hidden" or field.disabled or not name.replace("_", "").isalnum():
                    raise ValueError("Mapping names an unavailable form control")
                if len(value) > 10000:
                    raise ValueError("Mapped value is too long")
                locator = page.locator("form").first.locator(f'[name="{name}"]')
                if field.options:
                    if value not in field.options:
                        raise ValueError("Mapped value is not a current receiving option")
                    await locator.select_option(value)
                elif field.type in {"text", "email", "date", "textarea", "tel", "number"}:
                    await locator.fill(value)
                else:
                    raise ValueError("Unsupported form control requires assistance")
            for field in observation.fields:
                if field.required and not field.disabled and field.type != "hidden" and not request.values.get(field.name):
                    raise ValueError("A required receiving field has no approved value")
            expected_values = dict(hidden)
            for field in observation.fields:
                if field.disabled:
                    continue
                if field.type == "hidden":
                    if field.name not in hidden:
                        raise ValueError("An unrecognized hidden receiving field requires assistance")
                    continue
                if field.name in request.values:
                    expected_values[field.name] = request.values[field.name]
                else:
                    # An optional page default is not resident authorization.
                    existing = await page.locator("form").first.locator(f'[name="{field.name}"]').input_value()
                    if existing:
                        raise ValueError("A prefilled receiving value has not been approved")
                    expected_values[field.name] = ""
            form = page.locator("form").first
            post_url = await form.evaluate("form => form.action")
            expected_path = f"/portals/{request.portal_id}/tickets" + (f"/{request.ticket_id}/update" if request.action == "update" else "")
            self.policy.validate(post_url, portal_id=request.portal_id)
            if urlsplit(post_url).path != expected_path or urlsplit(post_url).query or await form.evaluate("form => form.method.toUpperCase()") != "POST":
                raise ValueError("Receiving action changed after the approved form was inspected")
            actual_values = await form.evaluate("form => Object.fromEntries(Array.from(new FormData(form).entries()).map(([k,v]) => [k, String(v)]))")
            if normalized_form_values(actual_values) != normalized_form_values(expected_values):
                raise ValueError("Receiving form values changed after approved facts were filled")
            # No HTTP write was permitted while loading/inspecting/filling. The
            # single permitted POST is now bound to the exact validated form.
            write_scope.arm_form_post(post_url, expected_values)
            async with page.expect_navigation(wait_until="domcontentloaded"):
                await page.locator('form button[type="submit"], form input[type="submit"]').first.click()
            # This is actual browser navigation after the portal commit. The agent
            # consumes a one-shot fault and SIGKILLs itself before receipt storage.
            accepted = await page.locator("script#ontara-receipt").count() == 1
            if not accepted:
                return BrowserResult(status="rejected", observation=observation, evidence={"tool": "playwright.submit", "reason": "no_receipt_marker"})
            if not request.return_receipt:
                return BrowserResult(status="accepted", accepted=True, evidence={"tool": "playwright.submit", "acceptanceObservedAt": now(), "receiptWithheldForCrashProof": True})
            receipt = await self._receipt(page, request)
            return BrowserResult(status="accepted", accepted=True, receipt=receipt, evidence={"tool": "playwright.submit", "receiptId": receipt["receiptId"], "ticketId": receipt["ticketId"], "acceptedAt": receipt["acceptedAt"]})
