# Municipal Roads research

Four frozen batches cover the 20 largest Ontario upper-tier governments by the summed 2021 Census populations of their actual lower-tier members. Halton was imported first. This is a **research directory**, with real source snapshots in Atlas; it is not province-wide live reporting access.

The core Atlas import and native-search gates passed on November 14, 2026: **20 upper tiers, 173 supporting lower tiers, 23 procedure/handoff records, 22 verified native-searchable records, 1 partial record excluded, 47 source references, 46 ready GridFS artifacts and 11 form snapshots**. All four core import runs are completed and search-ready. [Independent fresh-process audit](atlas_verification.json), [idempotent replay](replay_verification.json), [native search summary](../../scripts/retrieval/evidence/twenty-area-search-summary-20261114.json).

[Coverage matrix](coverage_matrix.md) · [160 cells and notes](coverage_matrix.json) · [CSV with source URLs](coverage_matrix.csv) · [Population ranking and all constituent counts](population_ranking_2021.json).

The matrix has 3 detailed published-procedure cells, 111 sourced handoffs, 1 partial handoff, and 45 explicit gaps. `verificationStatus: verified` verifies the published facts or handoff, not successful execution. Every procedure has `integrationStatus: research_only`. No email, call or report was sent to a real municipality. Official source URLs are separate from the demo execution allowlist.

Observed mandatory facts and fields are retained where published. Shell-only portals remain labelled as such. Renfrew's published concern form returned HTTP403; its source is unavailable and no obtained form artifact is claimed. General phone/email contacts do not prove a particular defect or asset is accepted. Sidewalk/curb responsibility, emergency handling, receipts and response targets remain unresolved where not sourced. A concern acknowledgement does not mean the issue was repaired.

## Stored evidence and boundaries

Sources preserve URL, observed time, extracted-text SHA256, immutable source version and artifact IDs. GridFS artifacts preserve actual obtained bytes, stored-byte SHA256 and ready status. Interactive form capture redacts hidden security values and nonces; source fingerprints and stored-file hashes have distinct meanings. Five core artifacts, including the Statistics Canada CSV, were independently read and hashed in a fresh process. Existing completed payloads replay without source rewrites or readiness resets.

The supplementary boundary batch contains WGS84 longitude/latitude GeoJSON for the 20 upper tiers, all 173 constituent lower tiers, and 14 supporting single-tier municipalities with no parent. It uses Ontario's official Land Information Ontario layers 13/14. The service generalized coordinates at 0.0001 degree; mainland, island and water parts were unioned, with logged repairs where generalization produced invalid parts. [Geometry checks and limits](boundary_geometry_verification.json), [provenance and repair log](boundary_summary.json). These are candidate-geography data; runtime location resolution and road ownership require separate verification. The supplementary Atlas import completed for all 207 geometries and six artifacts; see `roads-boundaries-20261114.result.json`. All six supplementary artifacts were re-read and SHA256 checked in a fresh process: [boundary Atlas audit](boundary_atlas_verification.json). The core 20-area audit was rerun afterward and retained all 22 native-search-ready versions.

The same supplementary payload retains the actual linked Middlesex County road-map PDF. Downloading and storing a map does not claim its layout was visually reviewed.

## Reproduction and import

All live database writes use the backend owner's validated `services/api/scripts/import_research.py` and GridFS interface. No research script writes collections directly. Native `voyage-4-large` Automated Embedding, `query.text` retrieval, search proofs and readiness are owned by the retrieval module. Research scripts never generate embedding arrays or call an embedding API.

The curation file is `roads_authorities.json`. Public batch files omit full obtained bytes/text; `source_cache/` and `*.import.json` are ignored. The latter are local complete import payloads with actual source artifact bytes. Credentials remain outside Git and are parsed by the backend settings loader; never source the private file as shell code.

The commands below replay an existing exact local payload from this build. A fresh checkout must first run `rank_upper_tiers.py` and `build_batches.py` for the desired authority IDs with a **new batch ID**, then validate/import that newly captured payload. The full local payloads are deliberately not in Git. With the backend installed, validate a complete local payload first:

```sh
python services/api/scripts/import_research.py --file data/municipal/roads-batch-01-20261114.import.json --validate-only
python services/api/scripts/import_research.py --file data/municipal/roads-batch-01-20261114.import.json --env-file ~/.config/ontara/mongodb.env
python scripts/municipal/verify_imports.py
```

`rank_upper_tiers.py` obtains the Ontario registry and Statistics Canada entire-table CSV; it joins CSD names within their census division and explicitly handles The Nation / La Nation. `build_batches.py` captures sources and builds backend-schema payloads; `review_sources.py` produces review excerpts without submitting forms; `export_coverage.py` checks and exports the frozen matrix. Boundary preparation uses existing research-tool `requests` and `shapely`; these are not added as app dependencies.

Batch IDs and `(source/procedure ID, sourceVersion)` are immutable. Reuse an existing exact payload for replay. A refreshed source or corrected curation requires a new batch ID and appropriate new versions; do not silently regenerate an already imported batch under its old ID. Complete the bounded checklist, then resume only for identified missing or stale facts.

## Sources and licences

Municipality status/membership: [Ontario Ministry of Municipal Affairs and Housing registry](https://data.ontario.ca/en/dataset/municipalities), June 2026 edition. Population: [Statistics Canada 2021 Census table 98-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000401). Boundaries: [Ontario municipal boundaries](https://data.ontario.ca/en/dataset/municipal-boundaries), under the [Open Government Licence Ontario](https://www.ontario.ca/page/open-government-licence-ontario). Municipal procedure facts are paraphrased from the official sources listed per record; full snapshots are stored as research evidence in Atlas and omitted from Git.
