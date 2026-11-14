# Atlas-native retrieval

Both approved indexes use `autoEmbed` on `retrievalText` with `voyage-4-large`.
The application supplies public text and metadata. Atlas creates and updates the
document embeddings and embeds `$vectorSearch.query.text` queries. There is no
application embedding endpoint, array or manual search fallback.

The recorded November 14 native diagnostic proof is in
[`evidence/native-preflight-20261114.json`](evidence/native-preflight-20261114.json).
It proves both indexes, text insertion/query, scope exclusions and automatic text
and version changes. The effective per-node settings were 1024 dimensions, scalar
quantization and cosine similarity. Internal generated records were inspected
read-only; they contained the new version and a 1026-byte BSON vector value. The
diagnostic records are explicitly partial synthetic knowledge and cannot satisfy
normal verified retrieval. This proof does not claim a successful municipal action
or replace the required verified event-day rehearsal lesson.

The reusable functions live in `services/api/app/retrieval`. Results are `ready`,
`pending` or `assistance_required`. Only up to three candidates reach the caller.
Every result is scoped to authority, issue, active category, public visibility,
current version and verification. Lessons also require the portal, workflow, form
family and form version. Expiry and live records are checked again after search.
Source verification and a matching native text/version proof are required before
returning a procedure. Research coverage never enables live submissions.

The API owner exposes these functions behind authenticated internal endpoints:

- `POST /internal/v1/retrieval/procedures`: `query`, `authorityId`, `issueId`,
  optional `categoryId` and `limit` (maximum three).
- `POST /internal/v1/retrieval/lessons`: the same fields plus `portalId`,
  `workflowKind`, `formFamily`, `formVersion`, and optional `withholdLessonIds`.
- Lesson admission uses `ProceduralLesson` and `promote_lesson`. Promotion verifies
  a real `receipt_verified` update operation with matching authority, issue,
  portal and observed form version. A seeded lesson retains its `seeded_demo`
  label. Shared text contains procedure semantics, never approved resident values.

An importer sets `searchStatus` to `pending` and clears `searchVerification` after
a material version/text change. `verify_record_search` then uses a native text
query prefiltered by the exact record ID and source version and conditionally
records proof only if the stored text/version is still unchanged. An ordinary
insert acknowledgement or a generally queryable index is insufficient.

From repository root with the API dependencies installed:

```sh
PYTHONPATH=services/api python -m pytest -q services/api/tests/retrieval
python scripts/retrieval/native_probe.py
python scripts/retrieval/verify_batch.py --input BATCH.json --output PROOF.json
```

The default native probe only reads readiness. `--ensure-indexes` creates missing
approved indexes; `--run-probe` explicitly inserts diagnostic records and updates
their text. Its bounded polling may return pending while Atlas finishes. Preserve
that state and retry later. Do not change a working index automatically.

Both scripts read `MONGODB_URI` from the environment or parse the owner-only
`~/.config/ontara/mongodb.env` as data. They never source it or print its values.
They require the runtime network path; a working managed connector alone does not
establish direct driver reachability.

Official references: [index configuration](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/),
[text queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/),
[automatic updates and generated storage](https://www.mongodb.com/docs/vector-search/crud-embeddings/automated-embedding/overview/).
