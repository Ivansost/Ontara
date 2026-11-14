# Staged hosted UI proof

This driver operates the real resident web interface on the Mac. All case, mail and execution processing must use the parent-verified hosted services. It never runs the executor locally, makes a standalone generation/embedding call, fakes a receiving receipt, or calls the internal follow-up-request endpoint.

Do not start while web/API/executor deployments are queued or failed. The coordinator verifies actual service URLs and readiness. Local API 8001 and local executor 8003 intentionally remain stopped during hosted proof.

## Ownership and private state

- Sol 1: resident UI, staged driver, screenshots, private browser session, mobile and session checks.
- Parent/Sol 2: case ledger and authenticated presenter fault/hold controls.
- Sol 4: genuine SIGKILL/fresh-process proof, executor run inspection, receiver counters and the same-run form change with the portal owner.
- Sol 6: genuine controlled AgentMail send/receive and operation correlation.

Run from `apps/web`. The driver uses the installed Google Chrome. It stores browser cookies in an owner-only directory outside the repository, defaulting to `~/.config/ontara/cloud-ui-qa/<run>/browser-session.json`. The manifest and screenshots are also owner-only. Never commit or print that session file. The internal token is read only in the Node test process from `ONTARA_INTERNAL_TOKEN` or `--private-env` (default `~/.config/ontara/cloud.env`); it is never passed to browser JavaScript, URL parameters, application source, screenshots or traces. The driver never enables tracing or HAR. At the coordinator’s request, `--record` captures only the resident page into an owner-only WebM under the private run directory; no terminal, admin request or browser toolbar is recorded. The matching Playwright FFmpeg must already be installed before recording a proof stage.

Treat the entire run manifest and session directory as private. Earlier captures may contain the exact receiving lookup tuple (run ID + operation/client reference + payload digest), which is a receiving capability. Never copy that tuple, raw JSON, lookup/ticket/update URLs or signatures into public media. Future driver summaries retain exact-match booleans rather than raw client-reference/digest values. Public media inputs are the resident page-only captures with Presenter evidence collapsed and the executor owner's separately sanitized proof. The driver omits signed update URLs, receipt signatures, raw operations, authorization headers and proposal explanations.

## 1. Prepare a fresh unapproved Roads draft

Use only URLs confirmed by the coordinator; these are explicit arguments, with no local API fallback:

```sh
node scripts/cloud-qa.mjs prepare-roads \
  --web https://ontara-web-35iy.onrender.com \
  --api https://ontara-api-35iy.onrender.com \
  --run hosted_roads_demo
```

The driver navigates category cards → Road surface → Pothole, uses the labelled synthetic location, confirms the incident location, answers authored questions, and presses **Review report**. It stops before checking approval or creating an operation. It prints the actual fresh case ID, case run ID and version. Share those IDs with Sol 2, Sol 4 and Sol 6. Do not reuse earlier local smoke cases.

The browser may close between stages; its private session persists. Reopening review uses **Review saved report → Details → Review report** through the real UI. Same-data PATCH is idempotent, and a material change still requires review of the actual resulting version.

## 2. Arm the deterministic controls before approval

Parent/Sol 2 use authenticated server-side controls on that unused draft:

- `POST /internal/v1/cases/{caseId}/fault-next-create` with `{ "kind": "kill_after_acceptance", "armed": true }`.
- `POST /internal/v1/cases/{caseId}/follow-up-hold` with `{ "held": true }`.
- `GET /internal/v1/cases/{caseId}/follow-up-hold` must show `held: true` and `nextCreateFaultArmed: true`.

Sol 4 confirms the deployed executor is ready and the receiving run still uses the initial v1 form. Keep v1 for the initial acceptance: do not preset v2 and do not rely on an eight-second mail interval. While held, the authority-question outbox must remain `HELD` with zero attempts, so no email or read-only inspection races the later form change.

After Sol 4's go:

```sh
node scripts/cloud-qa.mjs approve-roads --run hosted_roads_demo --recovery-ready
```

The driver confirms the persisted fault and hold, checks the real review checkbox, and clicks **Approve and send report**. The backend atomically transfers the fault to the first create operation before dispatch. The driver waits for a saved create receipt and joins recorded attempts: an actual `worker_process_exited` with exit code -9, its matching process start, and a later `receiving_lookup` from a distinct process birth/attempt. An unrelated read-only inspection start cannot satisfy recovery.

This stage stops after the initial reconciled receipt. It does not change the form or release mail.

## 3. Change v1 to v2 after reconciliation

Sol 4 independently checks executor runs and receiving presenter counters: one logical create, one ticket, and stable client reference/payload digest through the killed and recovered attempts. Then the parent/portal owner changes this exact case run's follow-up form from v1 to v2. The original accepted form remains v1.

Keep authority mail held through the coordinator's API restart and the separate, clearly labelled withheld-memory diagnostic. Sol 4 owns that read-only comparison: it must pause with zero generation-model calls and zero receiving updates. A diagnostic is not an authority email. The positive inspection must later come from the actual received provider question.

Only after the actual per-run v2 change, restart/held-state read-back and withheld comparison are confirmed, continue:

```sh
node scripts/cloud-qa.mjs follow-up-roads \
  --run hosted_roads_demo \
  --recovery-reviewed \
  --landmark "Synthetic demo community-centre sign"
```

Use a fact explicitly defined for the synthetic resident scenario. The driver will not invent a landmark.

This stage calls `POST /internal/v1/cases/{caseId}/follow-up-hold` with `{ "held": false }`. The API itself requires the initial saved receipt and fetches the configured same-run portal update schema, requiring actual v2 and its snapshot digest. The driver supplies neither a URL nor claimed evidence. Only then may the genuine authority question send and the read-only inspection run.

The driver polls existing durable mail work, requiring `AUTHORITY_QUESTION` for the initial create operation to be `SENT` and `RECEIVED`, with exact provider inbox/message/thread IDs and `evidence: message_read_from_controlled_receiving_inbox`. It does not manufacture a request or receipt.

The real case must then display the authored `nearestLandmark` question, backed by a positive validated mapping with selected lesson IDs and actual generation usage. A withheld diagnostic alone cannot satisfy this barrier. The driver fills only that known fact, presses **Review update**, checks fresh update approval, and clicks **Approve and send update**. It requires a new verified update receipt on the original ticket, native Voyage text-query/lesson evidence, actual generation usage, a recorded missing-landmark mapping followed by a complete approved mapping, and genuine `AUTHORITY_RESPONSE` plus `RESIDENT_NOTIFICATION` receiving evidence correlated to the update operation ID.

## 4. Separate Graffiti submission and responsive/security checks

After the Roads run reaches `roads_complete`:

```sh
node scripts/cloud-qa.mjs submit-graffiti --run hosted_roads_demo
node scripts/cloud-qa.mjs smoke --run hosted_roads_demo
node scripts/cloud-qa.mjs cancel-draft --run hosted_roads_demo
```

Graffiti uses a new case and the Public wall procedure through its distinct authored questions. It must obtain its own real receiving receipt; no Roads recovery fault is applied.

The cancellation stage creates one separate unused synthetic Roads draft, cancels through the normal case UI, verifies the cancelled state and hidden approval action, and sends one same-session approval probe that must return 409 with zero operations. It never approves that draft and preserves the successful Roads/Graffiti cases for review.

The smoke stage verifies nine category headings and zero horizontal overflow at 390 and 320 pixels; an HttpOnly/SameSite=Lax/Path=/ session cookie with Secure on HTTPS; denial from a fresh browser session; and proxy write-origin responses 403, 403 and 422. The 422 payload is intentionally incomplete and creates no case or operation.

## Interrupted checks

Do not repeat a create or approval merely because a response timed out. Inspect the authoritative case first:

```sh
node scripts/cloud-qa.mjs inspect --run hosted_roads_demo
node scripts/cloud-qa.mjs collect-roads --run hosted_roads_demo
node scripts/cloud-qa.mjs collect-update --run hosted_roads_demo
node scripts/cloud-qa.mjs collect-graffiti --run hosted_roads_demo
```

Collectors resume observing existing approved work without another approval or new case. They verify canonical server state rather than assuming a local manifest proves acceptance. A missing fact, unavailable model/retrieval, unsupported portal state or missing receiving proof stops the check; it is not converted to success. `--timeout-seconds` adjusts a bounded stage wait, capped at 900 seconds.

## Offline preparation checks

These use fixtures and make no backend, mail, generation or embedding calls:

```sh
node --test tests/cloud-qa-evidence.unit.mjs
npm run test:ui -- tests/cloud-driver.spec.ts
node scripts/cloud-qa.mjs help
```

The helper tests verify that UI preparation stops unapproved, distinguish a fresh recovery process from a read-only inspection, and require native retrieval plus exact received-mail correlation. They do not establish hosted execution success.
