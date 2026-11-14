# Independent demo receiving portals

This service contains **Regional Roads Portal — DEMO** (synthetic Halton pothole)
and **Local Municipality Portal — DEMO** (synthetic Milton public-wall graffiti).
It does not contact either municipality. Acknowledgement proves receipt of a test
report, not that an issue was repaired.

The receiver runs separately from the agent process. Tickets, receipts, form
versions, neutral HTML form snapshots, HTTP request evidence, and presenter-control
audit events live in `ontara_demo` on the event Atlas cluster. A create ticket and
its initial receipt are committed together in one document with majority write
concern. Updates append their immutable receipt and approved values to that same
ticket in one conditional atomic write. Restarting or killing the executor does
not erase receiving state.

## Run

From `services/portals`:

```sh
python -m pip install -r requirements.txt
python -m ontara_portals
```

Required server configuration:

| Variable | Purpose |
| --- | --- |
| `DEMO_PORTAL_MONGODB_URI` | Receiving database login; data always uses database `ontara_demo` |
| `DEMO_PORTAL_ADMIN_TOKEN` | At least 32 random characters; presenter-only bearer secret |
| `PORTALS_PUBLIC_BASE_URL` | Optional HTTPS origin override; otherwise Render's `RENDER_EXTERNAL_URL`, then local `http://127.0.0.1:8002` |
| `DEMO_PORTAL_RECEIPT_SECRET` | Optional separate HMAC key; defaults to presenter secret with signing-purpose separation |
| `PORT` | HTTP port; default 8002, Render provides its own value |

Local MongoDB credentials may be parsed from
`~/.config/ontara/mongodb.env` (override path with `ONTARA_MONGODB_ENV_FILE`).
The module starter also parses the selected non-database settings from
`~/.config/ontara/portals.env` (override with `ONTARA_PORTALS_ENV_FILE`).
Parsing uses `dotenv_values`; no credential file is sourced or executed. Real
values stay outside Git. Render uses server environment settings instead.

Build container from the repository root:

```sh
docker build -f services/portals/Dockerfile -t ontara-portals .
```

Render Free configuration: repository root build context, Dockerfile
`services/portals/Dockerfile`, health path `/healthz`. No local disk or paid service
is required. One Uvicorn process and a ten-connection MongoDB pool fit a small
receiving service; actual hosted memory/cold-start behavior still needs deployment
qualification. Uvicorn access logs are disabled because ticket URLs contain
capabilities.

The root `render.yaml` starts with this one free Oregon web service, automatic
deploys disabled, and three `sync: false` private values. It does not hardcode a
guessed public hostname or localhost into cloud configuration. The application
uses Render's documented `RENDER_EXTERNAL_URL` once deployed, including any suffix
Render assigns. `sync: false` prompts only during initial Blueprint creation;
later secret changes are supplied explicitly to the existing service.

## Browser contract

`portalId` is exactly `roads` or `graffiti`.

| Action | Route |
| --- | --- |
| Initial form | `GET /portals/{portalId}/new?runId=...&clientReference=...&payloadDigest=...` |
| Create through form | `POST /portals/{portalId}/tickets` |
| Reconcile receipt | `GET /portals/{portalId}/lookup?runId=...&clientReference=...&payloadDigest=...` |
| Read private test ticket | Receipt `ticketUrl` |
| Inspect current update form | Receipt `updateUrl`, append new `clientReference` and `payloadDigest` |
| Update same ticket | `POST /portals/{portalId}/tickets/{ticketId}/update` |

All forms use normal labels, native required inputs, selectable options, and a
submit button. Hidden inputs carry `runId`, `clientReference`, `payloadDigest`, and
`formVersion`; update forms also carry the ticket `accessToken`. A manually opened
new form generates a fresh synthetic run/operation. Executor callers supply the
existing approved operation identifiers. Do not create a new operation on retry.

Successful form POSTs return HTTP 201 (new acceptance) or 200 (already accepted).
The HTML contains visible ticket/reference/digest evidence and:

```html
<script id="ontara-receipt" type="application/json">{...}</script>
```

It contains a real stored receiver receipt, not client-generated confirmation.
The receipt includes `ticketId`, `receiptId`, `runId`, `portalId`, `authorityId`,
`routeId`, `clientReference`, `payloadDigest`, `action` (`create` or `update`),
`acceptedAt`, `formVersion`, `formPayloadDigest`, `formSnapshotDigest`,
`receiptSignature`, `receiptUrl`, `ticketUrl`, `updateUrl`, and `isDemo: true`.
Lookup of an update uses the update operation's new reference and digest and
returns that update's receipt for the original ticket. Exact mismatches return
409; absent receipts return 404. A 404 is absence at observation time, not blanket
permission to retry an uncertain write.

`payloadDigest` is the caller's SHA-256 of its canonical approved operation
payload. The receiver stores it unchanged, independently hashes the normalized
submitted form fields into `formPayloadDigest`, and binds both to its receipt.
Reusing a reference with a different digest, action, ticket, or submitted values
returns 409. Receiver HMAC signatures bind the receipt's critical fields. The
authoritative authentication check remains exact reconciliation with the
receiving interface; clients do not need the signing secret.

Ticket URLs contain random ticket-scoped access capabilities. Treat them as
private receipt data; redact their query parameters from logs/evidence shown to
others. Possessing a ticket ID alone does not permit reading or updating it.
No cookies or ambient resident credentials are used. Responses prohibit caching,
referrer propagation, scripts, framing, and third-party content.

## Form fields

Initial forms always use version 1, including after the update-form change.

| Form | Required | Optional |
| --- | --- | --- |
| Both initial forms | `location`, `description` | `reporterName`, `contactEmail`, `observedAt` (ISO calendar date) |
| Graffiti initial additions | `surfaceType`: Public wall / Underpass; `offensiveContent`: Yes / No / Not sure | Defaults: Public wall, Not sure |
| Roads/Graffiti update v1 | `location` | `additionalDetails` |
| Roads update v2 | `roadIntersection`, `travelDirection`, `roadPosition`, `nearestLandmark` | `additionalDetails` |

Direction options are Northbound, Southbound, Eastbound, Westbound, Not sure.
Position options are In travel lane, On shoulder, At curb, Not sure. Empty required
fields and unexpected fields/options are rejected server-side. The v2 form does
not derive new values from the old location. A stale unfinished v1 update is
rejected after mutation; the executor must inspect the current form and obtain
missing approved facts.

## JSON receiving API

The browser flow above is the demo execution path. JSON alternatives expose the
same receiver behavior for tests and receiving-interface integrations:

- `GET /v1/portals`
- `GET /v1/portals/{portalId}/form?runId=...&action=create|update`
- `POST /v1/portals/{portalId}/tickets`
- `GET /v1/portals/{portalId}/lookup?runId=...&clientReference=...&payloadDigest=...`
- `POST /v1/portals/{portalId}/tickets/{ticketId}/update`

POST bodies contain `runId`, `clientReference`, `payloadDigest`, `formVersion`,
`values` (a dictionary of visible field names to strings), and `accessToken` for
an update. Responses are the receipt plus `deduplicated` for POSTs. Browser
receipt JSON remains the exact persisted receipt.

## Presenter controls

All controls require `Authorization: Bearer <DEMO_PORTAL_ADMIN_TOKEN>`. This is a
separate receiver secret, not the app's `ONTARA_INTERNAL_TOKEN`. Never expose it
to the executor or public web bundle.

- `POST /internal/v1/runs` with `{ "runId": "demo-run-001", "label": "Final demo" }`
  creates that run idempotently; it cannot reset it.
- `POST /internal/v1/runs/{runId}/portals/roads/form-version` with
  `{ "version": 2, "expectedVersion": 1 }` changes only that run's unfinished
  Roads update. An unknown run is rejected, and a stale expected version is 409.
- `GET /internal/v1/runs/{runId}/evidence` shows each portal's
  `createRequestCount`, `ticketCount`, `updateRequestCount`,
  `acceptedUpdateCount`, `lookupRequestCount`, current form version and safe
  ticket summaries. It excludes resident/contact fields and access capabilities.
- Roads tickets can receive one presenter-authenticated simulated completion.
  [The resolution contract](RESOLUTION.md) defines the scoped mutation, private
  capability-protected status read, immutable replay and terminal update rules.
  It records **Resolved in demo**, with physical repair explicitly unverified.

Every validly identified incoming POST is a request attempt, including rejected
payloads and deduplicated attempts. A malformed envelope without valid run/reference
identifiers is rejected before assignment to a run. Tickets and accepted updates
are counted from actual receiving records. The executor must never use these
database/presenter counters as acceptance evidence. The crash test should show one
create request and one ticket after fresh-process reference lookup.

There is no global reset, deletion, worker kill, or fault endpoint. The executor
owner implements its authenticated one-shot process crash. Portal version changes
are independent, authenticated, per run and audited; other demo runs survive.

## Verification

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
```

The tests exercise create deduplication and changed-payload rejection, HTTP
requests versus ticket counts, exact receiving receipt lookup, real HTML forms,
same-ticket updates and their independent receipts, capability access, per-run
authenticated version changes, required v2 landmark, receiver restart, separate
Graffiti routing, snapshot storage, and secret redaction. Unit tests use mongomock;
actual Atlas/browser/cloud evidence is a separate integration gate.

For a running independent receiver, install `requirements-browser.txt`, install
Chromium using `python -m playwright install chromium`, and run:

```sh
python tests/browser_smoke.py --base-url http://127.0.0.1:8002 --artifacts-dir /tmp/ontara-portal-browser-proof
```

This uses real labelled HTML forms, fresh-browser receipt reconciliation, a
presenter-authenticated version change scoped to a fresh synthetic run, required
landmark validation, a same-ticket update, the separate Graffiti form, and
presenter counters. It does not test a killed agent process or Vector Search;
those remain separate execution gates. The generated report excludes capability
URLs. No run is reset or deleted.

After externally restarting the receiver process, run the script with
`--verify-existing-report /tmp/ontara-portal-browser-proof/browser-smoke.json` to
reopen those exact receipts in a new browser. This mode creates no new report or
update and checks that write counters and the changed form version survived.
For local development QA only, `--browser-channel chrome` uses an isolated
installed Chrome when the pinned Chromium download is unavailable. This does not
change the cloud executor's required bundled browser or prove its deployment.

Framework behavior follows current primary documentation:
[FastAPI forms](https://fastapi.tiangolo.com/tutorial/request-forms/),
[FastAPI test lifespan](https://fastapi.tiangolo.com/advanced/testing-events/), and
[PyMongo atomic updates/indexes](https://pymongo.readthedocs.io/en/stable/api/pymongo/collection.html).
