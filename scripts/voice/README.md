# Ontara voice foundation and historical browser proof

**Current direction — November 14:** the team requested removing voice from the
website and reserving ElevenLabs for future call-in intake. Browser microphone
controls, browser session linking and the browser SDK dependency are removed.
The API/provider foundation and private historical transcripts are retained;
no telephone number or call-in integration is configured. The browser behavior
and checks below document the earlier qualified extension, not a currently
available webpage feature.

Voice fills in the active report's existing authored questions. The resident
stops voice, checks the written report and named recipient, and uses the existing
versioned approval controls. There is no voice approval or submission tool.
Inactive categories never mount voice or call its API.

## Configuration

Set these **only on the API service**, through its private environment:

- `ELEVENLABS_API_KEY`
- `ELEVENLABS_AGENT_ID`
- `ONTARA_VOICE_ENABLED=true`

The web service needs no ElevenLabs secret. It forwards authenticated resident
requests through the existing same-origin API proxy. The API issues a provider
single-use signed URL with a reserved conversation ID. The SDK receives that
capability, never the workspace key. The intake buffer expires after ten minutes;
the configured provider conversation has a separate 180-second duration limit.

The historical browser build used `@elevenlabs/react` 1.22.1 (client SDK 1.36.1)
and a LiveKit CommonJS webpack alias. Both the browser dependency and its alias
have been removed. Astryx, StyleX, React, Next and the existing Babel
configuration remain in place.

The private ElevenLabs agent uses its **managed** `gemini-3.5-flash-lite` option,
not a custom LLM or a Google API key. Its English voice uses `eleven_flash_v2`.
It requires authentication, disables audio recording, retains provider transcripts
for seven days, limits a conversation to three minutes, and caps concurrency at
two and conversations at twelve per day. The API also limits a browser owner to
three issued sessions per UTC day and stops issuing sessions below 1,500 remaining
credits. No paid upgrade, phone number or telephone integration is configured.

Run `provision.py` with a private environment or `--env-file` to create/recheck
the named Ontara agent. `--update` explicitly reapplies the checked configuration.
It reuses an existing named agent and does not print credentials or signed URLs.
Do not place a credential-bearing env file in the repository.

## Consent, validation and storage

The microphone is requested only after the resident checks the voice consent
control and presses **Start voice**. Permission denial keeps the form usable.
Cancel, Stop, route exit and connection errors release the input; generation
fencing prevents an old permission request, SDK connection or tool response from
changing a newer attempt. Manual form edits stop the active voice input.

Only three client tools exist: `get_intake_state`, `record_answer` and
`skip_question`. The API accepts only the current visible authored question,
valid option values and the existing date/length validation. Required answers
cannot be skipped. Immediate danger stops normal intake. Model assertions grant
no authority. Voice cannot create an operation, approve, submit, contact an
authority or change a recipient.

`voice_sessions` stores the private consented intake buffer, canonical answers,
questionnaire version, fixed incident/recipient, reserved provider ID and status.
It never stores the signed capability. Normal web save creates/updates the case;
an owner-checked bind links voice history to that exact issue/location and case
version, without changing case content or approval. Material web edits continue
to invalidate approval through the existing API.

Only an actual provider conversation response can create a `call_records` entry.
The API fetches the transcript itself for its reserved conversation ID, verifies
the agent/conversation match, and retains role/message/timing fields in Atlas.
Client-provided transcript or arbitrary conversation IDs are not accepted.
Recording is disabled and its reference is null; no audio is invented or fetched.
History reads require the same private case owner. Private voice history never
enters `service_procedures`, `procedural_lessons` or shared vector memory.

Foreground transcript requests have bounded deadlines and do not block ordinary
reporting indefinitely. A small API lifecycle reader reconciles pending reserved
IDs after browser exit or API restart (at most three checks per tick, with a
lease and twenty-four checks per record). It only reads provider transcripts;
it cannot start a conversation, approve a report or dispatch a job. Atlas records
are retained through judging; this integration adds no automatic deletion.

## Verification

The requested `npx -y @elevenlabs/cli@latest onboard init` completed with the
privately supplied environment key. Authenticated account, subscription, model,
Agents and workspace-settings reads passed; private-agent creation, update and
single-use signed-session issuance also passed. The account was verified on the
Free tier; exact subscription usage is kept in the owner-only proof and handoff.
This does not establish Creator coupon redemption or an exhaustive API-key scope
inventory. Recheck the current balance after tests.

The controlled `text_smoke.mjs` uses real ElevenLabs model/tool responses and the
actual Atlas-backed case API. It answers the canonical questions, skips the
optional date, receives the named-recipient review, saves one synthetic unapproved
draft and links the actual provider transcript. It verifies fresh-session history
denial and no approved version/operation/submission. It uses no microphone and
produces no audio. Sanitized counts/booleans are in `evidence/`; full receiving IDs
and credentials stay outside Git. Text success does **not** establish audio or
microphone success.

The public build `a331330f` subsequently passed **one hosted browser audio test**
on November 14. Chrome used a synthetic audio device, not a real microphone.
The browser streamed the synthetic input, decoded/rendered non-silent provider
speech, saved the canonical `immediateDanger = No` answer, then stopped all input
tracks and its socket. The remaining form fields were completed manually and
saved as one unapproved review draft. No approval, operation, job or submission
was created by this test.

Independent read-only checks confirmed that the hosted API stored the actual
three-turn provider transcript in Atlas under the same private owner, incident,
case version and reserved conversation ID. The correct browser session read its
history with HTTP 200; a fresh session received HTTP 404. Recording remained off,
its reference was absent, and no audio artifact was stored. The local voice API
and transcript worker were stopped before this cloud test, so local processing
could not fill a missing hosted transcript.

See [browser audio evidence](../../../apps/web/scripts/cloud-qa/evidence/hosted-voice-20261114.json)
and [independent observer evidence](evidence/hosted-voice-observer-20261114.json).
The account remained on the Free tier at the timestamp in the observer evidence;
its exact usage was rechecked privately after the audio test. No paid upgrade or
credit redemption was performed. This is an observed check, not a future usage or
availability guarantee. The production build and all eleven combined browser
checks passed, including four voice guards; the combined API suite passed 153
tests. The public app remains at [Ontara](https://ontara-web-35iy.onrender.com).

For a loopback-only integration test, run `dev_api.py` using the existing API
environment. It explicitly disables mail and dispatch, listens on port 8027,
and accepts the local web preview on port 3027. Then run:

```sh
node scripts/voice/text_smoke.mjs
```

`services/api/tests/test_voice.py` covers question/branch guards, urgent handoff,
replay/limits, owner privacy, expiry, exact case linking, provider authenticity,
recording/capability checks, and transcript catch-up after restart. The removed
frontend `voice-intake.spec.ts` previously checked consent, denied/pending
microphone fallback, inactive isolation, retained manual approval, and bounded
transcript work. Current web checks verify written reporting and the absence of
microphone/provider calls. No browser test may use the user's real microphone
without their browser permission.

Official references: [onboarding/authentication](https://elevenlabs.io/docs/api-reference/authentication),
[React SDK](https://elevenlabs.io/docs/eleven-agents/libraries/react),
[private sessions](https://elevenlabs.io/docs/api-reference/conversations/get-signed-url),
[privacy](https://elevenlabs.io/docs/eleven-agents/customization/privacy).
