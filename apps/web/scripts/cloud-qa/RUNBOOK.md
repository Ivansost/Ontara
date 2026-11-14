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

## Ordinary Roads filing and email

There is no resident demo-mode switch. The ordinary site uses the configured synthetic Roads fixture. A normal run stops at its verified create receipt; it does not stage an authority question, crash or changed form. After reviewed deployments, the coordinator can run one bounded check:

```sh
node scripts/cloud-qa.mjs submit-roads \
  --web https://ontara-web-35iy.onrender.com \
  --api https://ontara-api-35iy.onrender.com \
  --run fresh_normal_roads \
  --notifications-env /Users/ivan/.config/ontara/agentmail.env \
  --require-email-receipt
```

`--notifications-env` must be an owner-only file outside the repository, containing `ONTARA_QA_NOTIFICATION_EMAIL` or the controlled test-resident `ONTARA_MAIL_RESIDENT_INBOX_ID`. An owner-set process environment `ONTARA_QA_NOTIFICATION_EMAIL` is also accepted. The address is entered in the real UI, stored only in private case/session state and omitted from CLI output. Do not put an address directly in the command or commit the private file. Screenshots/video remain private and may show the entered address.

`--require-email-receipt` is appropriate for a known controlled inbox that the mail worker can read: success requires actual receiving-inbox evidence. Without it, an opted-in run requires provider `SENT` and reports inbox delivery as unverified. No human-read or repair claim follows. If interrupted, use `collect-normal-roads --run fresh_normal_roads [--require-email-receipt]`; it observes the same known approved case and never creates or approves another. Keep any pending run intact.

The advanced stages below preserve the original crash/form-change story. Leave both notification configuration and `ONTARA_QA_NOTIFICATION_EMAIL` unset to reproduce its historical blank-email, three-message expectations. A new opted-in advanced run legitimately adds filing/information-needed notifications; it must not be forced into the old total.

## 1. Prepare a fresh unapproved Roads draft

Use only URLs confirmed by the coordinator; these are explicit arguments, with no local API fallback:

```sh
node scripts/cloud-qa.mjs prepare-roads \
  --web https://ontara-web-35iy.onrender.com \
  --api https://ontara-api-35iy.onrender.com \
  --run hosted_roads_demo
```

The driver navigates category cards → Road surface → Pothole, chooses the labelled synthetic location (which confirms that exact fixture), and answers authored questions on one page. The valid draft saves in the background. It stops at **Review and send**, before **Send report** or any operation. It prints the actual fresh case ID, case run ID and version. Share those IDs with the coordinator/execution/mail owners. Do not reuse earlier cases. An optional `--notifications-env PRIVATE_FILE` applies the same separately disclosed email opt-in as ordinary filing.

The browser may close between stages; its private session persists. Reopening uses the private case’s **Review saved report** button and returns to the one-page form. Same-data PATCH is idempotent, and a material change disables Send until its actual new version is saved and shown.

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

The driver confirms the persisted fault and hold, reads the inline recipient/facts/email disclosure, and clicks **Send report** once. That is the explicit approval. The backend atomically transfers the fault to the first create operation before dispatch. The driver waits for a saved create receipt and joins recorded attempts: an actual `worker_process_exited` with exit code -9, its matching process start, and a later `receiving_lookup` from a distinct process birth/attempt. An unrelated read-only inspection start cannot satisfy recovery.

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

The real case must display **One more detail** and the authored `nearestLandmark` question, backed by a positive validated mapping with selected lesson IDs and actual generation usage. A withheld diagnostic alone cannot satisfy this barrier. The driver fills only that known fact, reads its inline summary/recipient and clicks **Send update** once. Saving and approving that exact version happen behind this explicit action; a changed canonical answer or recipient stops before approval. It requires a verified update to the original ticket, native retrieval, actual generation usage, missing/complete mappings and the correlated authority response. Blank-email historical runs also require controlled resident receiving evidence; opted-in external destinations can establish provider acceptance only unless `--require-email-receipt` is supplied for a known controlled inbox.

## 4. Separate Graffiti submission and responsive/security checks

After the Roads run reaches `roads_complete`:

```sh
node scripts/cloud-qa.mjs submit-graffiti --run hosted_roads_demo
node scripts/cloud-qa.mjs smoke --run hosted_roads_demo
node scripts/cloud-qa.mjs cancel-draft --run hosted_roads_demo
```

Graffiti uses a new case and the Public wall procedure through its distinct authored questions. It must obtain its own real receiving receipt; no Roads recovery fault is applied.

The cancellation stage creates one separate unused synthetic Roads draft, cancels through the normal case UI, verifies the cancelled state and hidden approval action, and sends one same-session approval probe that must return 409 with zero operations. It never approves that draft and preserves the successful Roads/Graffiti cases for review.

After the coordinator authorizes it and the mail owner captures the completed state, `duplicate-mail --run hosted_roads_demo` repeats only the existing completed Roads hold release and durable mail catch-up. It requires unchanged case/operation/provider identities, one genuine authority-mail inspection and one update. Historical blank-email runs retain exactly three purposes and six stored copies. New opted-in runs require the applicable extra purposes without hardcoding an old total, with one attempt per outbox item. Output contains safe counters. This creates no case, approval, follow-up request or receiving write.

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
