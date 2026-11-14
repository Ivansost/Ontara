from html import escape
import json
from urllib.parse import urlencode

from .forms import PORTALS, fields_for


def page(title: str, body: str) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title><link rel="stylesheet" href="/assets/portal.css"></head><body><header><a href="/">Ontara demo receiving systems</a><p>DEMO — No real municipality receives these reports.</p></header><main>{body}</main><footer>Accepted reports demonstrate reporting progress. They do not mean that a real-world issue has been repaired.</footer></body></html>'''


def form_html(portal_id: str, action: str, version: int, envelope: dict, ticket_id: str | None = None, access_token: str = "", current_values: dict | None = None) -> str:
    portal = PORTALS[portal_id]
    target = f"/portals/{portal_id}/tickets"
    if action == "update":
        target += f"/{ticket_id}/update"
    hidden = {key: envelope.get(key, "") for key in ("runId", "clientReference", "payloadDigest")}
    hidden["formVersion"] = str(version)
    if action == "update":
        hidden["accessToken"] = access_token
    controls = "".join(f'<input type="hidden" name="{escape(key)}" value="{escape(str(value), quote=True)}">' for key, value in hidden.items())
    for field in fields_for(portal_id, action, version):
        # The changed form never reconstructs v1 values for its new fields.
        value = (current_values or {}).get(field.name, field.default)
        attributes = f'id="{field.name}" name="{field.name}"' + (" required" if field.required else "")
        if field.kind == "select":
            options = '<option value="">Choose an option</option>'
            options += "".join(f'<option value="{escape(option, quote=True)}"' + (" selected" if option == value else "") + f'>{escape(option)}</option>' for option in field.options)
            control = f'<select {attributes}>{options}</select>'
        elif field.kind == "textarea":
            control = f'<textarea {attributes} maxlength="{field.max_length}" rows="5">{escape(value)}</textarea>'
        else:
            control = f'<input {attributes} type="{field.kind}" maxlength="{field.max_length}" value="{escape(value, quote=True)}">'
        controls += f'<div class="field"><label for="{field.name}">{escape(field.label)}' + (" <span>(required)</span>" if field.required else "") + f'</label>{control}</div>'
    label = "Submit report" if action == "create" else "Submit update to this ticket"
    ticket_line = f'<p>Updating ticket <strong>{escape(ticket_id)}</strong>. This action does not create a new report.</p>' if ticket_id else ""
    return page(portal["title"], f'<h1>{escape(portal["title"])}</h1><p>{escape(portal["description"])}</p>{ticket_line}<p>Form version <strong>{version}</strong></p><form method="post" action="{target}" data-portal-id="{portal_id}" data-action="{action}" data-form-version="{version}">{controls}<button type="submit">{label}</button></form><p><a href="/portals/{portal_id}/lookup">Look up a receipt by client reference</a></p>')


def receipt_html(receipt: dict, deduplicated: bool = False) -> str:
    portal = PORTALS[receipt["portalId"]]
    title = "Report acknowledged" if receipt["action"] == "create" else "Update acknowledged"
    keys = [("Ticket", "ticketId"), ("Receipt", "receiptId"), ("Client reference", "clientReference"), ("Approved payload digest", "payloadDigest"), ("Submitted form digest", "formPayloadDigest"), ("Accepted at", "acceptedAt"), ("Action", "action"), ("Form version", "formVersion")]
    details = "".join(f'<dt>{escape(label)}</dt><dd><code>{escape(str(receipt[key]))}</code></dd>' for label, key in keys)
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    duplicate_note = '<p>This operation had already been accepted. The original receipt is shown.</p>' if deduplicated else ""
    return page(portal["title"], f'<h1>{escape(portal["title"])}</h1><h2>{title}</h2>{duplicate_note}<dl>{details}</dl><p><a href="{escape(receipt["ticketUrl"], quote=True)}">View this ticket</a></p><p><a href="{escape(receipt["updateUrl"], quote=True)}">Provide more information for this ticket</a></p><script id="ontara-receipt" type="application/json">{encoded}</script>')


def lookup_html(portal_id: str) -> str:
    return page(PORTALS[portal_id]["title"], f'<h1>{escape(PORTALS[portal_id]["title"])}</h1><h2>Look up a receipt</h2><form method="get" action="/portals/{portal_id}/lookup"><div class="field"><label for="runId">Demo run</label><input id="runId" name="runId" required></div><div class="field"><label for="clientReference">Client reference</label><input id="clientReference" name="clientReference" required></div><div class="field"><label for="payloadDigest">Approved payload digest</label><input id="payloadDigest" name="payloadDigest" required pattern="[a-f0-9]{{64}}"></div><button type="submit">Find receipt</button></form>')


def ticket_html(ticket: dict, update_url: str) -> str:
    fields = "".join(f'<dt>{escape(key)}</dt><dd>{escape(value)}</dd>' for key, value in ticket["currentValues"].items() if value)
    receipt_lines = "".join(f'<li>{escape(receipt["action"])} — {escape(receipt["receiptId"])} — {escape(receipt["acceptedAt"])}</li>' for receipt in ticket["receipts"])
    return page(PORTALS[ticket["portalId"]]["title"], f'<h1>{escape(PORTALS[ticket["portalId"]]["title"])}</h1><h2>Ticket {escape(ticket["ticketId"])}</h2><p>{escape(ticket["status"])}</p><dl>{fields}</dl><h2>Accepted actions</h2><ol>{receipt_lines}</ol><a href="{escape(update_url, quote=True)}">Provide more information for this ticket</a>')
