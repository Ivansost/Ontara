# Ontara deployment

The root `render.yaml` defines four **Free Oregon web services**. Automatic deploys
and preview environments are disabled. The coordinator owns all cloud changes,
Git integration, Blueprint planning/approval and deployment verification.

This configuration adds no Render database, Key Value service, persistent disk,
paid compute or Agent Engine workspace. The existing event Atlas Sandbox remains
the durable data layer. Agent Engine is the preferred architecture but its cloud
entitlement is not yet proven; the configured runtime is the selected supervised
Render fallback with one Atlas-backed LangGraph saver in the execution child.
This configuration alone does not prove a cloud browser launch or crash recovery.

## Services

| Blueprint name | Runtime and source | Health | Role |
| --- | --- | --- | --- |
| `ontara-portals` | Docker; repository context; `services/portals/Dockerfile` | `/healthz` | Independent synthetic receiving forms, receipts and per-run presenter controls |
| `ontara-web` | Native Node 22.15.0; `apps/web`; `npm ci && npm run build`; `npm run start` | `/api/health` | Next.js/Astryx site and same-origin API proxy |
| `ontara-api` | Docker; repository context; `services/api/Dockerfile` | `/readyz` | Cases, approvals, Atlas ledger, retrieval, mail and dispatch |
| `ontara-executor` | Docker; repository context; `services/executor/Dockerfile` | `/healthz` | HTTP supervisor, one active browser and the bounded execution child |

The portal definition is preserved from the first deployment wave. Its observed
service name is `ontara-portals-35iy` and its assigned URL is
`https://ontara-portals-35iy.onrender.com`. The Blueprint's logical name remains
`ontara-portals`; do not rename it or recreate the existing receiving service.

The API `/readyz` checks Atlas and normal index readiness, while `/healthz` is
process liveness. The executor's authenticated `/internal/v1/readyz` performs its
actual browser/runtime readiness check; public `/healthz` alone does not establish
execution readiness. Render supplies `PORT`, and all servers bind to `0.0.0.0`.

## Public HTTPS wiring

The Blueprint references each target's actual `RENDER_EXTERNAL_URL` through
`fromService.envVarKey`. These values include HTTPS and Render-assigned suffixes.
It references `RENDER_EXTERNAL_HOSTNAME` only for the browser's host allowlist.
It does not build public URLs from service names or `fromService.property: host`,
which is a private-network hostname.

| Consumer setting | Value supplied by Render |
| --- | --- |
| Web `ONTARA_API_URL` | API public HTTPS origin; server-only runtime proxy configuration |
| API `ALLOWED_ORIGINS` | Web public HTTPS origin |
| API `DEMO_PORTAL_BASE_URL` | Existing portal public HTTPS origin |
| API `ONTARA_EXECUTOR_BASE_URL` | Executor public HTTPS origin |
| Executor `BACKEND_BASE_URL` | API public HTTPS origin |
| Executor `EXECUTOR_BASE_URL` | Its own public HTTPS origin |
| Executor `PORTALS_BASE_URL` | Existing portal public HTTPS origin |
| Executor `ALLOWED_PORTAL_HOSTS` | Existing portal's public hostname without scheme |

The API derives `/internal/v1/run` from `ONTARA_EXECUTOR_BASE_URL`. The API owner
must merge that configuration support before this Blueprint is applied. An
explicit `ONTARA_AGENT_DISPATCH_URL` overrides the derived value; remove or update
any stale localhost value on an existing service. The Blueprint intentionally
omits that full-path override.

The web has no `NEXT_PUBLIC_*` API origin and no build-time API URL. Its
same-origin `/api/backend` route reads `ONTARA_API_URL` on the server and forwards
cookies in both directions. `SESSION_COOKIE_SECURE=true` is required for the
public HTTPS application.

Render documents public default-variable references in its
[Blueprint specification](https://render.com/docs/blueprint-spec.md#self-referencing-environment-variables)
and [default environment variables](https://render.com/docs/environment-variables.md).
Its [official frontend/backend example](https://github.com/render-examples/ai-hedge-fund-on-render/blob/main/render.yaml)
uses reciprocal `RENDER_EXTERNAL_URL` references for cross-service API and CORS
origins. References refresh on a Blueprint sync; an ordinary code-only redeploy
does not add a new `fromService` setting. Verify the resolved origins after the
reviewed sync.

## Private configuration

Real values are absent from source. `sync: false` prompts for initial values;
it preserves existing-service values on later syncs. Parent-owned private files
remain outside the repository and must be parsed as data, never sourced or
printed.

| Service | Manual variables | Private source / purpose |
| --- | --- | --- |
| Portals, existing | `DEMO_PORTAL_MONGODB_URI`, `DEMO_PORTAL_ADMIN_TOKEN`, `DEMO_PORTAL_RECEIPT_SECRET` | Existing receiver credentials and presenter/signing secrets; preserve them |
| API | `MONGODB_URI` | App login from `~/.config/ontara/mongodb.env`; database `ontara` |
| API | `ONTARA_INTERNAL_TOKEN` | Existing common internal bearer secret from the private runtime configuration |
| API | `AGENTMAIL_API_KEY` | Existing `~/.config/ontara/agentmail.env` key |
| API | `ONTARA_MAIL_INBOX_ID`, `ONTARA_MAIL_AUTHORITY_INBOX_ID`, `ONTARA_MAIL_RESIDENT_INBOX_ID`, `ONTARA_MAIL_ALLOWED_INBOX_IDS` | Three existing controlled inbox roles and their exact comma-separated allowlist |
| Executor | `GOOGLE_API_KEY` | Parent maps the existing private `GEMINI_API_KEY` to the runtime's expected name |

The executor receives the app `MONGODB_URI` and common `ONTARA_INTERNAL_TOKEN`
through references to the API's explicitly configured variables. It receives no
demo database URI, portal presenter secret or AgentMail API key. The API receives
no receiver database credentials or generation/Engine secret. This is application
configuration separation; the current broad Atlas database roles do not establish
database-enforced isolation.

The selected generation configuration is `google` / `gemini-3.5-flash-lite`, as
provided by the execution owner. The mail loop is enabled with an eight-second
poll interval and 60-message daily send budget. Only the three configured
controlled inboxes are allowed. Presenter fault controls remain internal bearer
operations; `ONTARA_ENABLE_DEMO_FAULTS=1` does not expose them publicly.

Do not set `ONTARA_ALLOW_LOCAL_HTTP`, a local browser channel, localhost URLs or a
second checkpoint saver in cloud configuration. The executor Docker image
installs its pinned Chromium. Root Docker context must exclude private env files,
credentials, development dependencies and local proof artifacts using the shared
root `.dockerignore` maintained by the integration owner.

## Reviewed rollout and verification

1. Merge the backend dispatch-origin support, API/mail slice, frontend and
   executor/agent sources so every declared path exists on remote `main`.
2. Validate the YAML against the current Render schema and inspect the actual
   Blueprint plan. The plan should preserve the existing portal and add only
   three free web services. Reject paid resources, removals or portal replacements.
3. The coordinator supplies only the required private manual values and applies
   the reviewed sync through the existing Blueprint. Keep Blueprint auto-sync and
   each service's automatic deploys disabled.
4. Ensure Atlas permits each service's observed outbound ranges. For the current
   Oregon service, the coordinator observed `74.220.48.0/24` and
   `74.220.56.0/24`; the user is adding these manually. Confirm the live service
   inventory and network path rather than treating a venue-Mac ping as cloud proof.
5. Wait for each deployment's terminal state. If an Atlas-dependent startup failed
   before access was added, restart/redeploy that service and recheck readiness.
6. Verify the web proxy and secure session cookie, API `/readyz`, portal forms and
   exact receipts, and authenticated executor browser readiness from the cloud.
7. Run a new synthetic Roads case: one create request, one ticket, genuine child
   process crash, fresh-process exact receipt reconciliation, changed follow-up
   form, native Atlas text-query lesson retrieval, newly approved landmark and a
   verified same-ticket update. Verify the real controlled mail loop and Graffiti
   route separately. Retain evidence and the deployed commit.

Free services can sleep after inactivity. Warm them through readiness checks
before presentation and qualify actual browser memory use and startup latency.
Do not silently substitute a paid plan, local execution or simulated recovery.

Current network behavior is documented in
[Render outbound IP addresses](https://render.com/docs/outbound-ip-addresses.md).
The Blueprint's shape is checked against the
[current public JSON schema](https://render.com/schema/render.yaml.json).
Structural validation does not replace the coordinator's platform-aware plan,
actual service build, network check or end-to-end execution proof.
