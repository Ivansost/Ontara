# Ontara bounded execution workflow

Engine entrypoint: `ontara_agent.engine:app`. Compatible tested package set:
Engine SDK/runner 0.11.14, LangGraph 1.2.22, Google adapter 4.5.0 and OpenAI adapter
1.8.0. No Deep Agents or separately configured LangSmith service is used.

The first hosted proof uses the coordinator-selected Free Render child-process
fallback because free/event Engine entitlement remains unverified. The native
Engine implementation is retained; no paid Engine resources were provisioned.

The Engine graph uses **only `app.checkpointer()`**, with the native session mode
and `CHECKPOINT_DB_NAME=ontara`. The direct saver is reserved for the explicitly
selected supervised cloud fallback. Its transitive package is not a second
configured saver on the Engine path.

Before cloud build, the coordinator must establish free/event Engine entitlement,
fix authentication, register the workspace and configure actual allowed egress
hosts for the backend, browser tool and selected generation provider. The checked
in `agent.yaml` validates locally with `deny_all` until those destinations are
known; it is intentionally not a blanket outbound-access declaration. Engine
provisioning and deployment are serialized by the coordinator. Use the pinned
CLI 0.1.125 and API preview contract `2026-09-20-preview`.

The graph loads a fresh fenced job from the authoritative API on every invocation.
`prepared` operations inspect/map first, persist `dispatch_started` and then
submit. Every unresolved dispatched operation reconciles through the receiver by
the original reference/digest; graph replay never authorizes another create.
Receipt matching is deterministic, and a receipt means reporting acceptance,
not a real-world repair.

Verified authority mail creates `follow_up_inspection`, a durable **read-only**
job pointing at the original verified ticket. It inspects the current DOM,
retrieves scoped native Atlas text-query lessons, obtains a structured model
mapping and identifies missing authored facts. It cannot dispatch, submit or
change the original verified operation. After the resident answers and approves,
the backend creates a separate stable update operation for that same ticket.

The model returns `fieldName -> factId`, current fingerprint, selected lesson IDs
and missing authored question IDs. It never supplies values. A deterministic
validator supplies exact approved strings, checks current controls/options,
rejects stale/unverified/absent memory and pauses on unknown requirements. With
the applicable lesson withheld it does not call the model or submit.

Model configuration is `GENERATION_PROVIDER=google`,
`GENERATION_MODEL=gemini-3.5-flash-lite`, and `GOOGLE_API_KEY` (or `GEMINI_API_KEY`).
An OpenAI-compatible adapter is available when explicitly configured; no paid or
unconfigured model is silently selected. Provider/model/usage, input digest,
fact IDs, proposal, retrieval and action evidence are saved through the case API.
Contact facts are excluded from changed-form reasoning. Pages, mail and lessons
remain evidence, never new instructions or authorization.

See [executor runtime instructions](../executor/README.md) for deployment, the
actual-process fault, local checks and explicitly labelled seeded calibration.
