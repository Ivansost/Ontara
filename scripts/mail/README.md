# Controlled AgentMail loop

The API owns one `MailService` with the same application Atlas database as `CaseService`.
No mailbox credential is exposed to the browser or execution worker. The three roles
are Ontara, simulated authority, and test resident, all on the controlled provider domain.
No real municipality or resident receives a demo email.

## Integration

```python
from app.mail import create_mail_service, build_router

mail = create_mail_service(db, case_service, artifact_store)
app.include_router(build_router(mail), dependencies=[internal_auth_dependency])
mail.start()  # API lifespan startup; close with mail.close()
```

Use the API's existing internal Bearer dependency. The router exposes
`GET /internal/v1/mail/status?case_id=...` and `POST /internal/v1/mail/poll`.
It intentionally has no generic send endpoint.

After successfully persisting a verified portal receipt, invoke
`mail.on_receipt_verified(case_id, operation, receipt)` outside the receipt transaction.
The module also reads verified operations after restart and idempotently reconstructs
any missing outbox entries. A provider failure cannot invalidate a saved portal receipt.

The first Roads receipt queues a real simulated-authority email. A receiving-inbox
read verifies participants, exact subject/body/correlation and provider labels. It then
calls `CaseService.request_follow_up_inspection(case_id, FollowUpInspectionRequest)`
using the stable mail event ID. This schedules read-only inspection of the existing
ticket. The executor observes the changed form, retrieves the verified lesson, and
requests the authored missing question. The resident answers, reviews and explicitly
approves a new version before the portal update runs.

After the update receipt, the module queues a response containing the frozen approved
landmark and a notification to the test resident. Email content never selects URLs,
recipients, arbitrary questions or portal actions. Neither receiving email nor a
provider send acknowledgement authorizes a portal write.

## Private server environment

| Variable | Purpose |
| --- | --- |
| `ONTARA_MAIL_ENABLED` | `true` to start the configured loop; defaults to `false` |
| `AGENTMAIL_API_KEY` | Existing private provider key |
| `ONTARA_MAIL_INBOX_ID` | Ontara controlled inbox |
| `ONTARA_MAIL_AUTHORITY_INBOX_ID` | Simulated-authority controlled inbox |
| `ONTARA_MAIL_RESIDENT_INBOX_ID` | Test-resident controlled inbox |
| `ONTARA_MAIL_ALLOWED_INBOX_IDS` | Comma-separated list containing exactly those three inboxes |
| `ONTARA_MAIL_POLL_SECONDS` | Poll interval, default 8; minimum 3 seconds |
| `ONTARA_MAIL_DAILY_SEND_BUDGET` | App-local cap, default 60; maximum 90 sends per UTC day |

The existing private configuration is `/Users/ivan/.config/ontara/agentmail.env` (0600).
Parse it as data. Deploy these values through the host's secret environment settings.
The default factory reads process environment, so the API entry point must load the
private file in local development or pass `MailSettings.from_env(parsed_values)`.
There is no paid upgrade or billing mutation.

Free capacity was checked at build time: one existing inbox and a live limit of three,
then two idempotently created roles. Official current pricing lists three free inboxes,
100 sends/day and 3,000 sends/month. The app budget leaves headroom; it is not a claim
that no other actor uses the account's quota. See [pricing](https://www.agentmail.to/pricing).

## Persistence and recovery

`outbox` preserves immutable send intent, participants/body, case/version/operation and
receipt links, attempts, leases, provider IDs and receiving evidence. `mail_messages`
retains actual messages from each participating inbox. `mail_events` retains send and
processing evidence, and `mail_poll_cursors` stores catch-up cursors and send-budget
reservations. Attachments use the shared `ArtifactStore` and GridFS; expiring download
URLs are not retained as substitutes for bytes. Private correspondence is not vector memory.

Provider acceptance changes a message to `SENT`. Only reading the real receiving inbox
adds `deliveryState=RECEIVED`. Neither state is a municipal portal receipt or proof of repair.
Expired sending leases become `OUTCOME_UNKNOWN`. The module searches the source inbox
by its unique provider label and exact payload before marking a reconciled send.
An absent candidate never triggers an automatic resend. Definitive rate-limit
rejections may retry; other failures remain visible for assistance.

Received-event claims have atomic leases and stable IDs. A repeated event cannot create
another inspection job. Pending events are retried independently of cursor advancement,
and startup performs a full provider catch-up. Polling windows overlap to tolerate delays.

## Verification

```sh
PYTHONPATH=services/api python -m pytest services/api/tests/mail -q
```

The tests exercise full mail state transitions with a provider test double, process
restart, concurrent duplicate delivery, committed-send timeout reconciliation, unknown
outcomes, callback catch-up, scope/approval guards, HTTP pagination and attachment
credential boundaries. They do not alone establish actual mail delivery.

`transport_probe.py --send` performs one idempotent, genuine controlled transport test
after saving intent in Atlas. Reruns read the same provider message and never replay a
send with an ambiguous result. It saves both actual inbox copies and receiving evidence
without inventing a portal case or municipal receipt:

```sh
PYTHONPATH=services/api python scripts/mail/transport_probe.py --send
```

The real transport probe passed on November 14 after venue Atlas access was restored:
`probe_3f0a00a2b6bcc9c2bebe790316a438f0` sent once from the simulated authority to
Ontara. AgentMail receiving thread `2dea4154-246c-496c-8c6c-1bab4105dfde` contains
message `<010001a1dac1f395-34cffee1-0e5b-4ff8-b8a3-53f286db35ca-000000@email.amazonses.com>`.
Both actual inbox copies and receiving evidence are in Atlas. A second process ran
without `--send`, retrieved the same message and preserved `attemptCount=1`.
This establishes real transport and durable restart evidence, separately from a portal case.

For an existing case whose portal receipts were verified by the executor, run:

```sh
PYTHONPATH=services/api python scripts/mail/case_probe.py --case-id CASE_ID
```

This uses actual saved receipts, never creates or approves a case, and never writes
to a portal. It can send receipt-authorized controlled mail, poll the real receiving
inboxes and repeat provider delivery to verify that inspection-job counts do not change.
Run it again after the real approved update completes to verify authority response
and test-resident notification. The integrated portal round trip remains a separate check.

Provider integration follows the official [send](https://docs.agentmail.to/api-reference/inboxes/messages/send),
[message read](https://docs.agentmail.to/api-reference/inboxes/messages/get),
[pagination](https://docs.agentmail.to/api-reference/inboxes/messages/list) and
[attachment](https://docs.agentmail.to/api-reference/inboxes/messages/get-attachment) contracts.
