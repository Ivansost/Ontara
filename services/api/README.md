# Case API

FastAPI and PyMongo provide the authoritative private case ledger, immutable versions,
explicit approval, durable jobs with expiring fenced leases, and Atlas evidence storage.
All external writes use a stable operation reference and approved-payload digest.
Uncertain dispatches require receiving-system reconciliation before retry.

## Run

Use Python 3.13, create a virtual environment, and install `requirements.txt`.
Supply the variables in `.env.example` through private environment configuration.
Production command from the repository root:

```sh
uvicorn app.main:app --app-dir services/api --host 0.0.0.0 --port "$PORT"
```

The repository-root Docker build uses `services/api/Dockerfile`, installs the pinned
runtime dependencies and runs as a non-root user. Set the Render health-check path to
`/readyz` and use a Free web service. The local Docker daemon was not used for validation;
the actual hosted image/network path must pass before claiming deployment readiness.

For local coordinated development only, `python services/api/scripts/run_local.py`
parses the existing private `~/.config/ontara/{mongodb,runtime,agentmail}.env` files as
data and starts at `http://127.0.0.1:8001`. It never executes those files as shell code.
Keep `SESSION_COOKIE_SECURE=true` on hosted HTTPS. Local HTTP requires false. The
Next.js app forwards `/api/backend/*` to this API without exposing internal secrets.

`/healthz` checks process readiness; `/readyz` requires the Atlas connection and normal
indexes. Startup leaves catalogue/questions/routing available when Atlas is unavailable,
but rejects case persistence until a successful restart establishes its connection.

## Contracts and access

`app/models.py` defines Pydantic request/response and research models. Regenerate the
public JSON catalogue, questions, JSON Schemas and OpenAPI with
`python services/api/scripts/export_contracts.py`. Shared contracts live in `contracts/`.

Resident `/v1` routes use a random opaque HttpOnly browser cookie, hashed for ownership
in Atlas. Case IDs alone grant no access. Cookies use SameSite=Lax, and public mutations
reject unapproved Origin and cross-site requests. Private responses disable caching.
All `/internal/v1` routes require Bearer `ONTARA_INTERNAL_TOKEN`.

Only configured Roads and Graffiti synthetic fixtures may create cases. Seven inactive
trees stop before intake. Municipality research does not enable external submissions.
Incident location drives responsibility; reporter residence does not override it.

`PATCH` and follow-up answer saves create immutable new versions and invalidate prior
approval. `/approve` authorizes the exact version, facts and recipient and creates one
stable operation plus durable job. Repeated approval cannot create extra work.
Cancellation revokes future actions without claiming to undo an accepted report.

## Runtime, mail and retrieval integration

Workers lease `/internal/v1/jobs/lease` and use the returned worker/token guard for
heartbeats, transitions and receipts. A new lease fences expired workers. Persist
`dispatch_started` before browser writes; reconcile it after a process exit. The
`abandon` endpoint requeues without resetting the operation. Presenter fault arming is
one-shot and restricted to prepared controlled-demo operations.

Authority email schedules a `follow_up_inspection` job with `readOnly=true`. The worker
inspects the current form and retrieves an applicable verified lesson before asking an
authored missing-fact question. Email never grants write approval. Resident answers
require another explicit approval before an update operation can exist. Inspection
results never mutate the already-verified create operation.

If `ONTARA_AGENT_DISPATCH_URL` is set, a restartable notifier scans durable queued jobs
and sends `{caseId,jobId}` with internal authentication. Notifications are retryable;
the Atlas lease controls execution. Leave this unset until the selected cloud runtime
has been verified. No in-memory job queue or Redis is required.

Mail and native retrieval are separate owned modules under `app/mail` and
`app/retrieval`. Mail receipt callbacks run after receipt persistence and are replayable.
Native Atlas Automated Embedding indexes and version probes belong to retrieval; this
API never supplies embedding arrays or marks imported procedures searchable by fiat.

Roads review includes the actual native retrieved published procedure and official
source versions. The published contact is research evidence; the approved action still
targets the clearly labelled controlled demo portal. Approval pauses if native retrieval
is unavailable or the source-backed route changed since review.

## Research and files

Validate and import versioned Roads knowledge with:

```sh
python services/api/scripts/import_research.py --file BATCH.json --validate-only
python services/api/scripts/import_research.py --file BATCH.json --env-file PRIVATE_ENV_FILE
```

The importer validates references, issue scope, immutable source/procedure versions,
and actual ready artifact links. Same batch/content replays are idempotent. Changed
content requires a new version and batch ID. It preserves source/form history, records
coverage/gaps in `import_runs`, and leaves search readiness pending for native probes.
`contentHash` on a source hashes its UTF-8 extracted text; file SHA-256 hashes actual bytes.

`ArtifactStore.put(ArtifactUpload)` stores bytes in GridFS bucket `ontara_files` with
pending/ready/failed metadata. It verifies hashes before publishing a ready reference,
serializes uploads, reconciles interrupted chunks, and deduplicates public content.
Private ownership remains separate. Required evidence belongs in Atlas, not temporary
Render disk. Never store authorization headers, cookies, credentials or hidden reasoning.

## Verify

Install `requirements-dev.txt`, then run `python -m pytest services/api/tests -q`.
Tests cover privacy, inactive bypass, stale approval, immutable versions, duplicate
approval, lease fencing, crash reclaims, exact receipts, inspection/approval ordering,
idempotent research import and GridFS ownership/hash behavior. Mongo mocks do not
establish real Atlas transactions, native search, receiving acceptance or cloud recovery;
those require the separately recorded live checks.
