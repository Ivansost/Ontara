# Ontara web

The resident web journey uses Next.js App Router, React 19, real Astryx components and the official Neutral theme. Residents complete reports with written form controls. It renders the backend-owned catalogue and question bank; generated copies live in `src/generated` and API types come from the backend OpenAPI schema.

## Run locally

Use Node 22.13 or later. From `apps/web`:

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Set server-only `ONTARA_API_URL` to the running case API (the coordinated local API uses `http://127.0.0.1:8001`). Open `http://localhost:3000`. `/api/health` returns the frontend's health independently of API readiness. Browser requests use the same-origin `/api/backend` proxy, which forwards the backend's HttpOnly session cookie. No provider, Atlas or internal API credentials belong in this app or in `NEXT_PUBLIC_` variables.

## Sync and verify

After the backend updates shared contracts, run these from `apps/web`:

```sh
npm run sync-contracts
npm run typecheck
npm run test:ui
npm run build
npm run astryx -- doctor --built .
```

The sync command also accepts a source directory: `npm run sync-contracts -- /absolute/path/to/contracts`. It requires canonical `catalogue.json`, `questions.json`, `municipalities.json` and `openapi.json`. During coordinated work a second argument may supply the municipality file from its separate data-owner checkout; generated copies are never hand-edited.

Browser tests use an installed Google Chrome. `navigation.spec.ts` exercises every inactive preview without API requests or data collection. `reporting.spec.ts` uses explicit browser-contract fixtures to check editing, fresh approval and same-case follow-up. `typed-intake.spec.ts` checks typed Roads and Graffiti review/resume flows and verifies no voice requests, microphone access or provider connections. These fixtures do not establish a live mailbox, execution worker or portal integration. A separate live browser smoke must verify those services after integration. To test the actual proxy and API origin checks without creating a case, run `ONTARA_LIVE_API_TESTS=1 npm run test:ui -- tests/proxy.spec.ts`. These tests disable request traces and assert cookie flags without logging cookie values. Set `ONTARA_TEST_BASE_URL` to the public HTTPS web origin to run the same checks after deployment; no local server is started in that mode.

## Render Free web service

The coordinator creates the service in the confirmed Render workspace:

- Runtime: Node; plan: Free.
- Root directory: `apps/web`.
- Build command: `npm ci && npm run build`.
- Start command: `npm run start`.
- Health check path: `/api/health`.
- Required environment: `ONTARA_API_URL` set to the deployed case API's HTTPS origin. It is server-only.
- Use a Node version meeting `engines.node`; Render supplies `PORT`, and the start script binds `0.0.0.0`.

The API must set its session cookie with `Path=/`, HttpOnly, SameSite=Lax and Secure on the hosted HTTPS deployment. Local HTTP uses Secure=false. The API's `ALLOWED_ORIGINS` must include the exact web origin. The proxy preserves `Origin` and `Sec-Fetch-Site` so the API's write-origin policy applies to browser writes. This app forwards Set-Cookie without rewriting its attributes or exposing its value to browser JavaScript. The cookie omits Domain, so a response through the web proxy belongs to the web host.

The coordinated Blueprint resolves `ONTARA_API_URL` from the API service's `RENDER_EXTERNAL_URL`, resolves API `ALLOWED_ORIGINS` from the web service's `RENDER_EXTERNAL_URL`, and sets API `SESSION_COOKIE_SECURE=true`. After deployment, verify the resolved origins and run the opt-in live proxy checks against the actual HTTPS web URL.

## Design and scope

Astryx core, Neutral and CLI are pinned to the same release. CSS reset, component production styles, theme production styles are imported once; the exact Neutral Figtree font family is self-hosted with Fontsource; app-specific responsive layout is compiled through StyleX's Babel/PostCSS integration. The frame derives from Astryx's documentation, form-wizard, detail-page and shell-top-nav templates. The generated Astryx instructions remain in `AGENTS.md`. The unchanged Figtree font license is available in `public/licenses/figtree.txt`.

Nine categories have dedicated nested routes. Seven inactive categories show empty disabled form previews and create no drafts. Active issues use one form with incident location, authored questions, optional email updates and an inline report/recipient review. Valid drafts save in the background; Send report explicitly approves the matching saved version. All 444 official Ontario municipalities appear in the searchable location selector, while only configured synthetic routes can submit. Notification email is separate from report contact and becomes fixed after first approval. The private case shows the actual receipt, email progress, a focused question and one Send update approval, cancellation and expandable presenter evidence. The final recipient is labelled DEMO; acknowledgement never means a repair.

Cases admitted to the server’s scripted email demonstration show a short cue for two simulated city emails: submitted, then resolved. The existing email area displays only recorded queued/send/delivery states. These scripted messages never change the case’s actual stage, receipt or repair status, and there is no extra resident page or approval step.
