"""Real-browser receiver contract check. Not an executor crash or memory demonstration.

Run from services/portals after the independent receiver is online:
    python tests/browser_smoke.py --base-url http://127.0.0.1:8002

Only labelled demo routes are contacted. Admin access changes one fresh run only.
No database handle, destructive reset or runtime-agent control is used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlencode, urlsplit

from dotenv import dotenv_values
import httpx
from playwright.sync_api import expect, sync_playwright


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def read_receipt(page) -> dict:
    expect(page.locator("#ontara-receipt")).to_be_attached()
    result = json.loads(page.locator("#ontara-receipt").text_content())
    assert result["isDemo"] is True
    for key in ("ticketId", "receiptId", "clientReference", "payloadDigest"):
        assert result[key] in page.locator("body").inner_text()
    return result


def public_receipt(receipt: dict) -> dict:
    # Deliberately exclude URLs and their ticket-scoped capability tokens.
    return {key: receipt[key] for key in ("ticketId", "receiptId", "runId", "portalId", "clientReference", "payloadDigest", "formPayloadDigest", "action", "acceptedAt", "formVersion", "formSnapshotDigest", "receiptSignature")}


def run(base_url: str, admin_token: str, artifacts: Path | None, browser_channel: str | None = None) -> dict:
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or parts.path not in {"", "/"} or not parts.netloc or parts.username or parts.query or parts.fragment:
        raise ValueError("Supply the independent demo receiver origin")
    run_id = "browser-smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
    auth = {"Authorization": "Bearer " + admin_token}
    report = {"runId": run_id, "baseUrl": base_url, "browserChannel": browser_channel or "bundled-chromium", "agentProcessCrashTested": False, "vectorMemoryTested": False, "checks": {}, "receipts": []}
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=base_url, timeout=45) as presenter:
        health = presenter.get("/healthz")
        health.raise_for_status()
        assert health.json()["isDemo"] is True
        result = presenter.post("/internal/v1/runs", headers=auth, json={"runId": run_id, "label": "Isolated browser smoke test"})
        result.raise_for_status()
        # A separate guard run proves mutations remain scoped.
        guard_id = run_id + "-guard"
        presenter.post("/internal/v1/runs", headers=auth, json={"runId": guard_id, "label": "Scope guard; no report"}).raise_for_status()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel=browser_channel)
            browser_context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = browser_context.new_page()
            page.set_default_timeout(20000)
            ref = "operation-create-" + secrets.token_hex(12)
            frozen = {"runId": run_id, "clientReference": ref, "payloadDigest": digest({"approvedSyntheticRoadsReport": ref})}
            page.goto(base_url + "/portals/roads/new?" + urlencode(frozen))
            expect(page.get_by_role("heading", name="Regional Roads Portal — DEMO", exact=True)).to_be_visible()
            page.get_by_label("Incident location", exact=False).fill("Synthetic Regional Road 25 / Example Drive, northbound at curb")
            page.get_by_label("Describe the problem", exact=False).fill("Synthetic pothole created only for this isolated browser test")
            if artifacts:
                page.screenshot(path=str(artifacts / "roads-initial-form.png"), full_page=True)
            page.get_by_role("button", name="Submit report", exact=True).click()
            initial = read_receipt(page)
            assert initial["clientReference"] == ref and initial["payloadDigest"] == frozen["payloadDigest"]
            report["receipts"].append(public_receipt(initial))
            report["checks"]["browserCreate"] = True
            # Close all prior browser context state, then read the saved receiver receipt.
            browser_context.close()
            browser_context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = browser_context.new_page()
            page.goto(initial["receiptUrl"])
            reconciled = read_receipt(page)
            assert reconciled == initial
            report["checks"]["freshBrowserReceiptLookup"] = True
            counts = presenter.get(f"/internal/v1/runs/{run_id}/evidence", headers=auth)
            counts.raise_for_status()
            roads_counts = counts.json()["portals"]["roads"]
            assert roads_counts["createRequestCount"] == roads_counts["ticketCount"] == 1
            report["checks"]["oneCreateRequestOneTicket"] = True
            mutation = f"/internal/v1/runs/{run_id}/portals/roads/form-version"
            assert presenter.post(mutation, json={"version": 2, "expectedVersion": 1}).status_code == 401
            presenter.post(mutation, headers=auth, json={"version": 2, "expectedVersion": 1}).raise_for_status()
            guard = presenter.get(f"/internal/v1/runs/{guard_id}/evidence", headers=auth)
            guard.raise_for_status()
            assert guard.json()["portals"]["roads"]["formVersion"] == 1
            report["checks"]["authenticatedPerRunMutation"] = True
            update_ref = "operation-update-" + secrets.token_hex(12)
            update_digest = digest({"approvedSyntheticFollowUp": update_ref})
            page.goto(initial["updateUrl"] + "&" + urlencode({"clientReference": update_ref, "payloadDigest": update_digest}))
            expect(page.get_by_label("Nearest landmark", exact=False)).to_be_visible()
            assert page.locator('input[name="location"]').count() == 0
            # These are test fixture expectations, not a mapping adapter used by the executor.
            page.get_by_label("Road or intersection", exact=False).fill("Synthetic Regional Road 25 / Example Drive")
            page.get_by_label("Direction of travel", exact=False).select_option(label="Northbound")
            page.get_by_label("Position on the road", exact=False).select_option(label="At curb")
            # Native validation must stop an unfinished update without the new required fact.
            assert not page.locator("form").evaluate("form => form.checkValidity()")
            page.get_by_label("Nearest landmark", exact=False).fill("Approved synthetic community sign")
            if artifacts:
                page.screenshot(path=str(artifacts / "roads-changed-form.png"), full_page=True)
            page.get_by_role("button", name="Submit update to this ticket", exact=True).click()
            updated = read_receipt(page)
            assert updated["ticketId"] == initial["ticketId"] and updated["clientReference"] == update_ref
            assert updated["action"] == "update" and updated["formVersion"] == 2
            report["receipts"].append(public_receipt(updated))
            report["checks"]["requiredLandmarkSameTicketUpdate"] = True
            page.goto(updated["receiptUrl"])
            assert read_receipt(page) == updated
            report["checks"]["updateReceiptLookup"] = True
            graffiti_ref = "operation-graffiti-" + secrets.token_hex(12)
            graffiti_frozen = {"runId": run_id, "clientReference": graffiti_ref, "payloadDigest": digest({"approvedSyntheticGraffiti": graffiti_ref})}
            page.goto(base_url + "/portals/graffiti/new?" + urlencode(graffiti_frozen))
            expect(page.get_by_role("heading", name="Local Municipality Portal — DEMO", exact=True)).to_be_visible()
            page.get_by_label("Incident location", exact=False).fill("Synthetic Milton public wall at Example Park")
            page.get_by_label("Describe the problem", exact=False).fill("Synthetic graffiti for this isolated browser test")
            page.get_by_label("Public structure", exact=False).select_option(label="Public wall")
            page.get_by_label("Does it contain offensive content?", exact=False).select_option(label="Not sure")
            page.get_by_role("button", name="Submit report", exact=True).click()
            graffiti = read_receipt(page)
            assert graffiti["portalId"] == "graffiti" and graffiti["authorityId"] == "milton-town"
            report["receipts"].append(public_receipt(graffiti))
            report["checks"]["separateGraffitiReceiver"] = True
            if artifacts:
                page.screenshot(path=str(artifacts / "graffiti-receipt.png"), full_page=True)
            browser_context.close()
            browser.close()
        final_counts = presenter.get(f"/internal/v1/runs/{run_id}/evidence", headers=auth)
        final_counts.raise_for_status()
        evidence = final_counts.json()
        assert evidence["portals"]["roads"]["createRequestCount"] == evidence["portals"]["roads"]["ticketCount"] == 1
        assert evidence["portals"]["roads"]["updateRequestCount"] == evidence["portals"]["roads"]["acceptedUpdateCount"] == 1
        assert evidence["portals"]["graffiti"]["createRequestCount"] == evidence["portals"]["graffiti"]["ticketCount"] == 1
        report["evidence"] = evidence
    if artifacts:
        (artifacts / "browser-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def verify_existing(report_path: Path, base_url: str, admin_token: str, browser_channel: str | None = None) -> dict:
    """Reopen stored references after an external receiver restart, without a write."""
    previous = json.loads(report_path.read_text())
    run_id = previous["runId"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=browser_channel)
        page = browser.new_page()
        for expected in previous["receipts"]:
            query = {key: expected[key] for key in ("runId", "clientReference", "payloadDigest")}
            page.goto(base_url + f'/portals/{expected["portalId"]}/lookup?' + urlencode(query))
            assert public_receipt(read_receipt(page)) == expected
        browser.close()
    with httpx.Client(base_url=base_url, timeout=45) as presenter:
        result = presenter.get(f"/internal/v1/runs/{run_id}/evidence", headers={"Authorization": "Bearer " + admin_token})
        result.raise_for_status()
        counts = result.json()
        for portal_id in ("roads", "graffiti"):
            for counter in ("createRequestCount", "ticketCount", "updateRequestCount", "acceptedUpdateCount"):
                assert counts["portals"][portal_id][counter] == previous["evidence"]["portals"][portal_id][counter]
        assert counts["portals"]["roads"]["formVersion"] == 2
    return {"runId": run_id, "receiptsVerifiedAfterReceiverRestart": len(previous["receipts"]), "writeCountersUnchanged": True, "roadsFormVersion": 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--admin-env-file", default="~/.config/ontara/portals.env")
    parser.add_argument("--artifacts-dir")
    parser.add_argument("--browser-channel", choices=["chrome"], help="Explicit local QA fallback to installed Chrome; cloud uses the image's bundled Chromium")
    parser.add_argument("--verify-existing-report", help="Read a prior browser-smoke.json after externally restarting the receiver; performs no submissions")
    args = parser.parse_args()
    private_path = Path(args.admin_env_file).expanduser()
    private = dotenv_values(private_path) if private_path.is_file() else {}
    token = os.environ.get("DEMO_PORTAL_ADMIN_TOKEN") or private.get("DEMO_PORTAL_ADMIN_TOKEN") or ""
    if len(token) < 32:
        raise SystemExit("Provide the private presenter secret through the environment or an owner-only env file")
    try:
        if args.verify_existing_report:
            report = verify_existing(Path(args.verify_existing_report).expanduser(), args.base_url.rstrip("/"), token, args.browser_channel)
        else:
            report = run(args.base_url.rstrip("/"), token, Path(args.artifacts_dir).expanduser() if args.artifacts_dir else None, args.browser_channel)
    except Exception as exc:
        # Browser exceptions may contain full capability URLs; keep them out of stdout.
        raise SystemExit("Browser receiving-system check failed (" + type(exc).__name__ + "). Inspect the service/test state privately; no capability URL was printed.") from None
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
