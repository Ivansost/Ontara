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
The private presenter control can hold one synthetic Roads case's authority question
in `HELD` with zero send attempts. Its durable flag and bounded audit live on that
case, separate from resident facts, version and authorization. Normal cases have no
hold. The worker rechecks the flag before sending and before scheduling an inbound
inspection. A restart preserves the hold; a committed release with interrupted outbox
repair is recovered by the next poll. Other cases continue normally.
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
and test-resident notification.

### Integrated real-mail evidence — November 14

The integrated synthetic case `case_edf099cb47c54a4eaa56c17c5b5785ed` completed
the genuine controlled mail round trip. Both portal receipts refer to the same
ticket `RDS-A6F3F3D7E435`; the verified update receipt is
`RCP-1975CF64438CD905F9943233`. The mail module did not create a case, approve facts,
lease an inspection or dispatch a portal action during verification.

- Authority question, authority response and test-resident notification each have
  `state=SENT`, `deliveryState=RECEIVED`, and `attemptCount=1`.
- Six actual message copies, with actual text/participants/provider IDs, are retained
  in Atlas. The authority response arrived on the original authority thread
  `eedecc93-a270-43d3-b6d4-8979c625e527`; the resident notification was read from
  the controlled test-resident inbox.
- The genuine mail event created exactly one read-only inspection job. A separate,
  explicitly labelled withheld-lesson inspection accounts for the second inspection
  record; it is not a duplicate email event. One approved portal-update operation exists.
- A fresh mail-service process performed full provider catch-up and a repeated poll:
  six duplicate messages, zero newly processed events, zero pending/errors, and
  unchanged inspection-job counts. No extra send or portal operation was created.

This evidence verifies controlled mail and the persisted case links. Portal acceptance
comes from the separate verified receiving-system receipts, and repair remains unverified.

The compact sanitized [evidence JSON](evidence/case_edf099cb47c54a4eaa56c17c5b5785ed.json)
contains provider IDs, receiving-inbox proof, same-ticket receipt IDs and restart/dedup
counts. It contains no message bodies, capability/session URLs or tokens. Regenerate
an artifact for an existing synthetic case with `capture_evidence.py --case-id CASE_ID`;
the script performs provider catch-up but never sends mail or creates a receipt.

## Hosted demo: existing-case follow-up

One controlled hosted Roads case completed this sequence through the real web UI,
receiving portal, Atlas state and AgentMail. The [compact cloud summary](evidence/cloud-mail-summary.json)
records the full loop, actual API-restart persistence and authorized duplicate replay.
The [sanitized timeline](evidence/cloud-case_a8853b60c3ce4b6db35bfca6e7b21ab6.json)
contains independent GET observations at the stage barriers. Coverage remains the
configured synthetic demo; issue repair is unverified.

1. The API server has the private AgentMail variables above, its internal token, Atlas
   access, and the executor dispatch configuration. Use the same three controlled inbox
   roles. The presenter prepares the applicable verified native lesson and the run's
   original follow-up form version 1. A browser session creates the synthetic Roads
   draft, then stops before approval.
2. Set the private durable hold on that existing draft before UI approval:

   ```sh
   PYTHONPATH=services/api python scripts/mail/trigger_followup.py \
     --api-url https://ACTUAL-API-HOST.onrender.com \
     --case-id case_EXISTING_DRAFT_CASE_ID \
     --runtime-env /Users/ivan/.config/ontara/runtime.env --hold
   ```

   Substitute the actual `case_` identifier with its 32 hexadecimal characters. The
   helper reads `ONTARA_INTERNAL_TOKEN` from the private file or process environment;
   it never accepts a token in command-line arguments or prints it. The file is parsed
   as data. A loopback origin is also accepted for development; hosted origins require
   HTTPS on Render. HTTP redirects are not followed with the token.

   This uses Bearer-only `POST /internal/v1/cases/{case_id}/follow-up-hold` with
   `{"held":true}`. Read back `GET` on the same path and require `held:true`; the backend
   also returns `nextCreateFaultArmed` for the separately armed presenter crash control.
   Neither control nor token appears in the public browser flow.
3. The resident explicitly approves the report in the UI. The executor submits against
   the original version 1 workflow, genuinely crashes after acceptance, then reconciles
   the saved initial receipt. The authority email remains durably `HELD` with
   `attemptCount:0`; no timed delay or incoming-mail inspection can bypass that barrier.
4. After receipt reconciliation, the presenter changes this **same run's** follow-up
   form from version 1 to version 2 through the portal owner's authenticated mutation
   control. Then release this case:

   ```sh
   PYTHONPATH=services/api python scripts/mail/trigger_followup.py \
     --api-url https://ACTUAL-API-HOST.onrender.com \
     --case-id case_EXISTING_VERIFIED_CASE_ID \
     --runtime-env /Users/ivan/.config/ontara/runtime.env --release-hold
   ```

   The API accepts only `{"held":false}`. It verifies this run's saved initial
   `receipt_verified` operation and fetches the update-form schema from its configured
   portal origin, requiring the same run, Roads/update, form version 2 and snapshot
   digest. The caller cannot provide an arbitrary URL or claimed mutation evidence.
   The release updates only private control metadata and queues that case's one
   authority message; repeats are safe. It changes no report facts, version or approval.
5. The helper authenticates `GET /internal/v1/cases/{case_id}` and
   `GET /internal/v1/operations/{currentOperationId}` before ordinary mail polling.
   It refuses an absent receipt, unmatched operation, unverified state, live route,
   cancelled case or still-active hold. It invokes `POST /internal/v1/mail/poll` and reads
   `GET /internal/v1/mail/status?case_id=...` until the authority email has genuine
   `deliveryState=RECEIVED`. The polling endpoint runs the existing mail replay/send
   loop for configured controlled inboxes; it is not a generic email send endpoint.
6. The receiving event schedules the existing case's read-only inspection. The hosted
   executor observes the form, retrieves the native lesson, and asks the authored
   missing landmark in the same private browser session. The resident answers, reviews
   and explicitly approves the new version. Only then does the existing execution
   workflow update the same ticket and verify its receipt. That receipt queues the
   controlled authority response and test-resident notification.
7. Inspect internal mail status for three `SENT`/`RECEIVED` records and their provider
   receiving evidence. Repeat the helper safely: stable outbox/message/event identities
   prevent another send or inspection. Hosted read-only evidence capture uses:

   ```sh
   PYTHONPATH=services/api python scripts/mail/capture_cloud_evidence.py \
     --api-url https://ACTUAL-API-HOST.onrender.com \
     --case-id case_EXISTING_VERIFIED_CASE_ID --label demo_observation
   ```

   This observer makes authenticated GET requests only. It saves full receiving
   observations under the owner's private `~/.config/ontara/evidence` directory
   (0700, files 0600). Public artifacts replace raw receiving run/operation/client
   references and digests with aliases and exact-match booleans. Message bodies,
   session/capability URLs and tokens are excluded.

The hosted evidence verifies a durable draft hold, actual crash and receipt recovery,
an actual API redeploy while the authority outbox stayed `HELD` at zero attempts,
the same run's v1→v2 change and separately labelled withheld-lesson comparison,
then guarded release and the genuine mail-driven positive flow. The resident answered
and approved version 2 in the ordinary UI; the same ticket acknowledged one update.
All three emails have genuine receiving-inbox evidence, one attempt each and six
stored message copies. One authorized repeat-release/mail-catch-up exercise returned
zero sends/new processing and two duplicate events; the independent after observation
preserved the same provider/outbox identities, one real inspection and one update.

The helper never creates a case, fabricates a receipt, edits an answer, grants approval,
leases an inspection or dispatches a portal action. If a read-only job remains queued,
the executor owner resumes the configured workflow; do not create a question directly
to skip the inspection. The completed local rehearsal cases were subsequently cancelled;
the helper correctly refused them without posting or sending another email.

Provider integration follows the official [send](https://docs.agentmail.to/api-reference/inboxes/messages/send),
[message read](https://docs.agentmail.to/api-reference/inboxes/messages/get),
[pagination](https://docs.agentmail.to/api-reference/inboxes/messages/list) and
[attachment](https://docs.agentmail.to/api-reference/inboxes/messages/get-attachment) contracts.
