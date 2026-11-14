# Ontara execution service

This authenticated service runs one isolated Playwright browser task at a time
against the two configured **DEMO** portals. Browser writes use normal HTML forms;
recovery obtains exact receipts through the receiver's lookup interface. It never
reads the receiving database or contacts a real municipality.

`services/agent` contains the bounded LangGraph workflow. The coordinator selected
the documented **Free Render fallback for the first hosted proof** because free
or event-covered Engine entitlement is not established. Engine code remains
available for qualification. In the fallback this service runs the same graph in
a separate, killable child process and survives
the child's actual `SIGKILL`. In either mode the case API's Atlas operation ledger
controls authorization, leases, dispatch state and verified receipts.

## Endpoints

All `/internal/v1/` routes require `Authorization: Bearer ONTARA_INTERNAL_TOKEN`.
The receiver presenter token is separate and is never given to this service.

| Route | Purpose |
| --- | --- |
| `GET /healthz` | Process health and selected runtime mode |
| `GET /internal/v1/readyz` | Actual isolated Chromium launch/readiness |
| `POST /internal/v1/browser/inspect` | Read current form labels, types and options |
| `POST /internal/v1/browser/submit` | Validate fingerprint and submit approved values |
| `POST /internal/v1/browser/reconcile` | Exact reference/digest/action receipt lookup |
| `POST /internal/v1/run` | Notify execution with `{jobId,caseId,recover:true}` |
| `GET /internal/v1/runs/{taskId}` | Safe transient supervisor/invocation status |

The browser context binds `operationId`, `caseId`, `runId`, `attemptId`,
`portalId`, `clientReference`, `payloadDigest`, `action`, and for updates the
original `ticketId`/private `updateUrl`. Submit additionally requires the exact
observed `formFingerprint` and approved string `values`. The caller is the
authenticated bounded workflow. User/page/model text cannot select an arbitrary
host or action. Redirects and asset requests outside the configured origin are
blocked. Private capability query parameters are redacted from observations.

## Build and configure

Build from the repository root:

```sh
docker build -f services/executor/Dockerfile -t ontara-executor .
```

The image pins Python 3.12, Playwright 1.65.2 and its matching Chromium revision;
`playwright install --with-deps chromium` installs Linux system dependencies.
Use the root build context and exclude private `.env` files from the Docker
context. Render configuration is a **Free web service**, one Uvicorn process,
health path `/healthz`, no persistent disk. The coordinator provisions/deploys it.

Required server variables are `ONTARA_INTERNAL_TOKEN`, `BACKEND_BASE_URL`,
`EXECUTOR_BASE_URL`, `PORTALS_BASE_URL`, `ALLOWED_PORTAL_HOSTS`, and
`ONTARA_RUNTIME_MODE=engine|fallback`. All deployed URLs use HTTPS.

Engine mode also requires `AGENT_ENGINE_CLIENT_ID`, `AGENT_ENGINE_CLIENT_SECRET`,
`AGENT_ENGINE_PROJECT_ID` and `AGENT_ENGINE_WORKSPACE_ID`. The internal notifier
exchanges a service-account token and invokes the pinned
`2026-09-20-preview` API contract; it never treats the app's internal token as
Engine authentication. A stable job-scoped Engine session and the application
ledger permit a fresh invocation to reconcile an unresolved operation.

Fallback mode additionally needs the app `MONGODB_URI`,
`CHECKPOINT_DB_NAME=ontara`, `GENERATION_PROVIDER`, `GENERATION_MODEL` and the
chosen provider credential. It uses exactly one direct Atlas `MongoDBSaver` in
the child. The parent receives the child's exact lease guard through a private
pipe; after process exit it requeues that lease without changing the operation
reference/digest/state, then launches one fresh child. There is no in-memory
production database or local-Mac live execution mode.

`ONTARA_ENABLE_DEMO_FAULTS=1` enables the separately authenticated, one-shot
presenter fault consumed by the backend lease. The child first persists
`dispatch_started`, submits the actual browser form, observes the receipt marker,
and `SIGKILL`s its own OS process before parsing or recording the receipt.
The independent receiver stays alive. The fresh process performs lookup rather
than another create. Missing/ambiguous lookup evidence pauses; it is never
permission for a blind retry. `ONTARA_LEASE_SECONDS` defaults to 15, with a
heartbeat every five seconds; the direct fallback also releases a dead child's
lease immediately using its fencing guard.

## Local development checks

Local tests are development verification, not the cloud execution deliverable.
The starter parses allowlisted values from private `mongodb.env`, `gemini.env`
and `runtime.env` as data. It does not import the demo database credential.

```sh
python -m pip install -e 'services/agent[fallback,test]' -e 'services/executor[test]'
python -m playwright install chromium
PYTHONPATH=services/agent/src:services/executor/src python -m pytest services/agent/tests services/executor/tests
PYTHONPATH=services/agent/src:services/executor/src PORT=8003 ONTARA_ALLOW_LOCAL_HTTP=1 python -m ontara_executor
```

An explicit development-only `ONTARA_LOCAL_BROWSER_CHANNEL=chrome` can use an
isolated installed Chrome while the matching binary downloads. Deployed builds
use the pinned Chromium and reject this override unless local HTTP testing was
explicitly enabled.

The test suite checks current-option/fact validation, absent/stale/unverified
memory, read-only mail inspection ordering, unknown outcomes and a real OS
process kill followed by fresh-process reconciliation. The crash unit fixture
uses file-backed fake receiver/ledger data; actual Atlas, Playwright and hosted
process evidence are separate integration gates.

## Seeded calibration

`scripts/calibrate.py` is a standalone developer rehearsal, never an HTTP route
or runtime branch. Supply an external JSON object mapping current observed field
names to immutable approved fact IDs and an already approved synthetic **update**
job. It records explicit `manual_seeded_demo_calibration` provenance, performs
the actual Playwright update and records the matching receiver receipt through
the API. An unresolved rerun reconciles rather than repeating the update.

```sh
PYTHONPATH=services/agent/src python services/executor/scripts/calibrate.py \
  --job-id job_APPROVED_UPDATE --mapping /private/path/mapping.json \
  --private-env /private/path/runtime.env --seeded-demo-calibration
```

This establishes disclosed `seeded_demo` knowledge with actual event-day receipt
evidence. Promotion/search readiness is owned by the retrieval API. It is not
presented as memory-guided runtime adaptation. The runtime still requires native
retrieved verified memory plus a generation-model mapping for changed forms.
