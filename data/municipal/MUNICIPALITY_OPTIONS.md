# Ontario municipality selector directory

[`contracts/municipalities.json`](../../contracts/municipalities.json) contains every row in the current English [Ontario Ministry of Municipal Affairs and Housing municipality registry](https://data.ontario.ca/en/dataset/municipalities), verified on November 14, 2026: **444 municipalities — 241 lower tier, 173 single tier and 30 upper tier**. The English CSV edition is dated `2026-05-26` in its published filename. Ontario's CKAN metadata identifies June 3, 2026 as the resource's last modification; the exact URL, observation time and SHA-256 are frozen in [`municipality-options.sources.json`](municipality-options.sources.json).

This is location selection metadata. Inclusion does not establish Roads research coverage, an integration, geocoding, asset responsibility or permission to submit a report. Existing research/import counts and the controlled demo route allowlist remain independent. This directory is not an Atlas import payload.

## Contract and labels

The top-level object has `version`, `source`, `counts` and `options`. Each option has the following fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable Ontara municipality identifier. All 207 previously imported identifiers are preserved. |
| `label` | Readable selector label; a lower-tier municipality includes its actual upper tier. |
| `name` | Registry name with the trailing municipal form removed when the registry supplies one. |
| `tier` | `lower`, `single` or `upper`, from the registry's municipal status. |
| `type` | Municipal form: `city`, `town`, `township`, `village`, `municipality`, `county`, `regional-municipality`, `district-municipality` or `united-counties`. |
| `upperTierId`, `upperTierName` | Actual parent identifier and display name for lower tiers; `null` for single and upper tiers. |
| `geographicArea` | Unchanged registry geographic area. This does **not** assign single-tier municipalities a parent. |
| `aliases` | Original registry name and, when applicable, the same name reordered as “Town of Milton”, for example. |

Milton is the lower-tier town `milton-town`, labelled **Milton, Halton Region**, with parent `halton-region`. Halton and Peel also have their own upper-tier options. Toronto and Hamilton city are single-tier municipalities with no parent. Hamilton township remains a distinct lower-tier municipality in Northumberland County. Brant County, Haldimand County, Norfolk County and Prince Edward County are single tier despite “County” in their names.

Regional municipality labels use “Region”; county labels use “County”; united counties and the District Municipality of Muskoka retain their municipal form in the label. The registry's three names without a trailing `, … of` form — Haldimand County, Norfolk County and The Nation Municipality — are preserved. New identifiers use an ASCII name slug plus municipal form; known imported identifiers take precedence, including the existing The Nation identifier.

The array is alphabetized by a case-insensitive ASCII-folded label, then identifier. It contains no selected value or demo fixture. The frontend may pin Milton as a clearly labelled demo choice and should search `label`, `name`, `aliases` and `geographicArea`. Changing the selection must clear any previous fixture and location confirmation; the normal backend route check still decides whether intake is supported.

## Extent

All 444 municipal corporations in the official registry are included, including all 30 upper-tier governments as directly selectable regions/counties. This is not a list of every named Ontario community or geographic district. Northern geographic districts are not added as upper-tier municipal governments. Unorganized territories, First Nations reserves, neighbourhoods and other places absent from this registry use the existing manual-location fallback; their absence is not a claim that they have no responsible reporting authority. Single-tier geographic areas must not be converted into parent relationships.

## Validation and refresh

The standard-library validator makes no network requests and performs no database or application writes:

```sh
python -B data/municipal/validate_municipality_options.py
```

It checks the frozen directory hash, source metadata agreement, official counts, unique identifiers and labels, sorting, every lower-tier parent and every existing imported identifier/parent. It also checks the Milton demo identifiers and the single-tier/municipal-name distinctions above.

For a complete row-by-row comparison, download the official CSV to a temporary location and pass it explicitly:

```sh
curl --fail --location --output /tmp/ontara-municipalities-en-2026-05-26.csv 'https://data.ontario.ca/dataset/62e83cbc-0731-4d66-abdc-2f2b31bcd76c/resource/6783a586-6b05-4a73-9663-e60a6963c91e/download/municipalities_-_en_2026-0526.csv'
python -B data/municipal/validate_municipality_options.py --source-csv /tmp/ontara-municipalities-en-2026-05-26.csv
```

That comparison checks the exact source bytes and recreates all options deterministically. The verified source contains exactly the columns `Municipality`, `Municipal status` and `Geographic area`. HTML anchor text is decoded; only lower-tier rows are joined to an upper-tier row by the registry geographic area. Alias text preserves the original official name. No website links, contacts, procedure records or boundaries are inferred.

Before refreshing, inspect the current [official dataset metadata](https://data.ontario.ca/api/3/action/package_show?id=municipalities), obtain its English resource, review changes and preserve existing identifiers. Update the canonical file, source manifest, counts and verification time together, then run both validations. The frontend owner synchronizes this contract into its generated data using the existing contract-copy process; the generated copy must not be curated separately.

Contains information licensed under the [Open Government Licence – Ontario](https://www.ontario.ca/page/open-government-licence-ontario).
