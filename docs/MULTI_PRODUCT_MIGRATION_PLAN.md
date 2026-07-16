# DropFinder multi-product migration plan

## Status

Design and implementation contract for the staged migration from the current THCA-flower-only pipeline to a type-aware product marketplace.

This document is intentionally the first pull request in the stack. No production scraper, catalog, or UI behavior changes should merge before the schema, vendor coverage, retrieval, parsing, publication, and test boundaries below are accepted.

## Goals

1. Migrate the existing flower pipeline into one generalized product model.
2. Support one active product type at a time in search and browsing.
3. Preserve multiple type tags for mixed products such as a THCA + mushroom gummy.
4. Add category-specific fields and category-specific normalized price metrics.
5. Add a compact-row terpene field to every cannabis product type.
6. Extract terpenes from product pages, linked COA pages, COA-only indexes, and COA documents whenever a vendor publishes them.
7. Publish incomplete optional data with an em dash in the UI and a transparent completeness score rather than inventing values.
8. Require saved fixtures, live smoke tests, parser contracts, negative-classification tests, and browser tests for every configured website.
9. Keep blocked live tests non-blocking only after the worker attempts the documented public retrieval ladder and records evidence for the block.
10. Cover every current website plus `https://calicanna.cc/` in the first migration contract and acceptance matrix.

## Product taxonomy

Every record has one `primary_type` and one or more `type_tags`.

Stable primary types:

- `cannabis_flower`
- `cannabis_vape`
- `cannabis_edible`
- `psilocybin_mushroom`
- `psilocybin_vape`

`type_tags` may contain more than one type. A mixed THCA + mushroom gummy can use:

```json
{
  "primary_type": "cannabis_edible",
  "type_tags": ["cannabis_edible", "psilocybin_mushroom"]
}
```

The primary type controls the active marketplace view, required fields, normalized price metric, compact-row layout, and sort behavior. Secondary tags remain visible and searchable only inside the selected primary-type view. The UI must never combine multiple primary-type result sets in one search.

## Common product contract

Every admitted product and variant carries:

- stable product and variant identities
- vendor identity
- canonical public product URL when the category permits an outbound commerce link
- source product and variant identifiers when published
- source title and normalized display title
- `primary_type`
- `type_tags`
- current price
- original price when valid
- explicit stock state
- image URL when public
- normalized quantity and unit appropriate to the primary type
- normalized comparison metric
- completeness score
- field-level provenance
- collection timestamp
- classification evidence
- optional document references

Missing optional values remain `null` in data and render as `—`. The parser must not substitute guessed values, zeroes, generic labels, or values inherited from unrelated variants.

## Type-specific fields and comparison metrics

### Cannabis flower

Compact row:

- vendor
- product name
- type tags
- lineage
- total THC / THCA display retained from the migrated flower contract
- package weight
- terpenes
- current price
- price per gram
- stock
- completeness score

Expanded details retain flower variants, effects, environment, potency provenance, terpene breakdown, and COA documents.

Comparison metric: `price_per_gram`.

### Cannabis vape

Compact row:

- vendor
- product name
- type tags
- device type
- volume
- terpenes
- current price
- price per milliliter
- stock
- completeness score

Expanded-only fields:

- puff count
- COA documents and extracted analytes

Explicitly excluded fields:

- device compatibility
- cannabinoid summary field
- rechargeable flag
- blend ingredients

Comparison metric: `price_per_ml`.

### Cannabis edible

Compact row:

- vendor
- product name
- type tags
- piece count
- total labeled active amount
- amount per piece
- terpenes
- current price
- price per 100 mg of labeled active amount
- stock
- completeness score

Explicitly excluded fields:

- format
- cannabinoid summary field
- flavor
- ingredients
- allergens
- serving size

Expanded details may show source labels, variant labels, terpene breakdown, and COA documents, but may not reintroduce excluded normalized fields.

Comparison metric: `price_per_100mg`.

### Psilocybin mushroom

Compact row:

- vendor
- product name
- type tags
- species
- strain
- weight
- claimed or tested potency
- current price
- price per gram
- completeness score

Expanded details:

- COA documents and extracted analytes
- field provenance
- source claims separated from laboratory measurements

Comparison metric: `price_per_gram`.

### Psilocybin vape

Compact row:

- vendor
- product name
- type tags
- volume
- device type
- psilocybin percentage
- current price
- price per milliliter
- completeness score

Expanded details:

- COA documents and extracted analytes
- field provenance
- source claims separated from laboratory measurements

Comparison metric: `price_per_ml`.

## Controlled-product boundary

The application may index public informational metadata for psilocybin products, but the normalized shopper publication must not expose outbound purchase links for controlled psilocybin products. Source URLs may be retained in non-public operator provenance when needed for reproducible parsing and testing.

No age gate, jurisdiction gate, dosage advice, or promotional safety badge is introduced by this migration.

## Completeness scoring

Completeness is calculated per primary type. It is not a confidence score and it does not convert source claims into verified facts.

Recommended weighting:

- 35% common commerce fields: title, vendor, price, stock, image, valid quantity
- 45% type-specific shopper fields
- 20% evidence quality: product-level evidence, field provenance, and document linkage

Rules:

1. The score is an integer from 0 to 100.
2. Missing optional fields reduce the score but remain publishable as `null`.
3. Missing identity, type evidence, a valid public price, or variant identity remains a hard rejection.
4. Each field has a provenance state: `structured`, `product_page`, `document_page`, `coa_document`, `derived`, or `missing`.
5. Derived values require all inputs and retain the formula and source references.
6. The compact row shows the score; expanded details show missing fields and provenance.

## Terpene and COA extraction contract

Terpene extraction applies to every cannabis primary type.

Source priority:

1. structured storefront fields
2. structured product-page JSON or JSON-LD
3. explicit product-page text or tables
4. linked COA landing pages
5. vendor COA-only indexes matched by product, batch, SKU, variant, or canonical URL
6. COA HTML tables
7. text-bearing PDF documents
8. image-only documents through a bounded OCR fallback only when deterministic text extraction is unavailable

Required normalized output:

- individual terpene names
- individual percentages or published units
- total terpene percentage when explicitly published or safely derived from compatible analyte units
- dominant terpenes ordered by amount
- source document URL or stable operator reference
- batch, SKU, product, and variant scope
- extraction method
- collection timestamp
- confidence and match evidence

Parser rules:

- Never attach a COA by title similarity alone when a stronger batch, SKU, product ID, or canonical URL key exists.
- Never mix analytes from different batches or variants.
- Preserve raw analyte labels and units alongside normalized names and values.
- Reject impossible percentages and incompatible unit aggregation.
- Keep source-claimed potency separate from lab-measured potency.
- Record unmatched and ambiguous documents for operator diagnosis.

## Public retrieval ladder for blocked automation

A vendor route is attempted through public, bounded methods in this order where applicable:

1. official Shopify product or collection JSON
2. official WooCommerce Store API
3. public vendor JSON endpoints embedded in the storefront
4. category HTML and JSON-LD
5. product sitemap discovery followed by product-detail retrieval
6. embedded application state in public HTML
7. public COA index and document routes
8. alternate public canonical storefront host or vendor-owned CDN
9. a bounded browser-rendered smoke route when static retrieval cannot expose the public data

The worker must not bypass authentication, CAPTCHAs, access controls, or private APIs.

A live test may be marked non-blocking only when:

- the saved fixture and parser contract remain blocking and pass;
- at least two applicable public retrieval methods were attempted;
- the final status records HTTP status, content type, route, retry count, and block signature;
- no stale live response is treated as current success;
- the vendor remains visible in source health as blocked or quarantined.

## Website coverage matrix

Every row below is required in this first contract and in the first retrieval implementation PR. Each website requires product-type route discovery, saved fixtures, parser assertions, negative fixtures, a live smoke result, and a source-health receipt.

| Source ID | Vendor | Required domain | Existing platform hint | Migration requirement |
|---|---|---|---|---|
| `arete` | Arete | `arete.shop` | HTML storefront | Discover every publicly listed supported type; preserve explicit block reporting. |
| `black_tie_cbd` | Black Tie CBD | `blacktiecbd.net` | HTML / collection storefront | Add type-specific collection and product-detail routes. |
| `crysp` | Crysp | `crysp.co` | WooCommerce + HTML | Expand Store API and detail parsing; include COA-linked terpene extraction. |
| `five_leaf_wellness` | Five Leaf Wellness | `fiveleafwellness.com` | WooCommerce + HTML | Scan storewide with strict type evidence and cross-type negative tests. |
| `green_unicorn_farms` | Green Unicorn Farms | `greenunicornfarms.com` | WooCommerce + HTML | Preserve fallback routing while adding type-specific routes. |
| `hello_mary` | Hello Mary | `shophellomary.com` | WooCommerce + HTML | Add public category and product-detail routes for all supported types sold. |
| `holy_city_farms` | Holy City Farms | `holycityfarms.com` | WooCommerce + HTML | Expand smokeables and edible/vape discovery where publicly present. |
| `loud_house_hemp` | Loud House Hemp | `loudhempproducts.com` | WooCommerce storewide | Require strict per-type evidence because discovery is storewide. |
| `lucky_elk` | Lucky Elk | `luckyelk.com` | Shopify | Add collection discovery and product JSON coverage by type. |
| `preston_herb_co` | Preston Herb Co. | `prestonherbco.com` | HTML storefront | Add product sitemap/detail fallback and explicit empty/block states. |
| `pure_roots_botanicals` | Pure Roots Botanicals | `purerootsbotanicals.com` | WooCommerce + HTML | Add all public supported-type categories and COA matching. |
| `quantum_exotics` | Quantum Exotics | `quantumexotics.com` | HTML storefront | Add category/detail discovery and complete fixture coverage. |
| `secret_nature` | Secret Nature | `secretnature.com` / `secretnaturecbd.com` | Shopify | Resolve canonical host, discover supported collections, and retain 404/empty evidence. |
| `sherlocks_glass` | Sherlocks Glass & Dispensary | `sherlocksglass.com` | WooCommerce | Add strict type classification to prevent accessories from entering product results. |
| `smoky_mountain_cbd` | Smoky Mountain CBD | `smokymountaincbd.com` | WooCommerce | Add all supported public categories and document parsing. |
| `stoney_branch_farms` | Stoney Branch Farms | `stoneybranch.com` | Shopify | Expand storewide classification and per-type variant parsing. |
| `wnc_cbd` | WNC CBD | `wnc-cbd.com` | HTML storefront | Add sitemap/detail and alternate public route attempts before marking blocked or empty. |
| `cali_canna` | Cali Canna | `calicanna.cc` | To be discovered | Add as a first-class source with platform detection, product-type routes, product-detail parsing, fixtures, live smoke tests, and source-health reporting. |

A source does not pass migration because one category works. The source-level receipt must report results independently for every supported type the website publicly lists.

## Test matrix

All five layers are required.

### 1. Saved real-product fixtures

- At least one positive fixture per vendor and publicly sold supported type.
- At least one negative cross-type fixture per vendor.
- COA fixtures where the vendor publishes documents.
- Fixtures retain response metadata and are scrubbed of cookies, authorization material, and personal data.

Blocking in CI: yes.

### 2. Live website smoke tests

- Attempt every required vendor.
- Exercise every discovered route family.
- Verify content type, HTTP result, candidate count, accepted count, rejection count, and document count.
- Use the public retrieval ladder before recording a block.

Blocking in CI: yes for deterministic parser or contract failures; non-blocking only for documented live access blocks under the rules above.

### 3. Parser contract tests

- Common identity, stock, price, variant, quantity, and URL parsing.
- Every type-specific field.
- Every normalized price metric.
- Terpene names, units, totals, dominant ordering, and provenance.
- COA product/variant/batch matching.
- Completeness scoring and em-dash presentation contract.

Blocking in CI: yes.

### 4. Classification and contamination tests

- Positive and negative evidence for each primary type.
- Mixed-type tagging.
- Accessories, generic mushroom supplements, non-product pages, and unsupported forms cannot leak into results.
- A product appears under exactly one primary-type search view.
- Secondary tags do not duplicate a record across views.

Blocking in CI: yes.

### 5. Browser and publication tests

- One product-type selector is always active.
- Search state resets safely when product type changes.
- Compact columns and expanded details change by type.
- Cannabis rows expose terpene summaries.
- Puff count and vape COA remain expanded-only.
- Missing values render as `—`.
- Completeness score is visible and accessible.
- Sorting uses the active type's comparison metric.
- Mixed-type tags render without placing a product in multiple active views.
- Mobile Chromium, mobile WebKit, desktop Chromium, Firefox, and WebKit remain covered.
- Static publication remains deterministic and generation-safe.

Blocking in CI: yes.

## Migration and rollback

The current flower-only data remains a read-only rollback input while the generalized catalog is built and verified.

The migration is forward-only at the schema boundary:

1. Convert current flower records into the generalized source record.
2. Run type-aware admission and field extraction.
3. Build a new catalog generation with type-specific compact indexes and shared detail shards.
4. Update the UI to load exactly one type index at a time.
5. Keep the existing flower publication available until the new generation passes parity and live-source acceptance.
6. Roll back by selecting the previous manifest generation, not by translating generalized data back into the old flower schema.

Byte-for-byte compatibility with the old flower catalog is not required. Product and variant identity continuity is required where the underlying source identity is unchanged.

## Pull request stack

### PR 1: contract and UI plan

- This document.
- Detailed UI behavior and responsive layout specification.
- All-vendor acceptance matrix.
- No production behavior changes.

### PR 2: generalized source schema and classifier

- Primary type and multi-type tags.
- Common and type-specific source records.
- Quantity and metric normalization.
- Completeness scoring.
- Existing flower migration and regression fixtures.

### PR 3: all-vendor retrieval, product parsing, terpenes, and COAs

- Every website in the matrix, including `calicanna.cc`.
- Public retrieval ladder.
- Per-vendor/per-type fixtures.
- COA-only page matching and document extraction.
- Live smoke receipts and blocked-route reporting.

### PR 4: generalized catalog publication

- Type-specific compact indexes.
- Shared details and document shards.
- Generation hashing and verification.
- Rollback manifest.

### PR 5: marketplace UI implementation

- Single active product type.
- Type-specific compact rows, filters, sorting, and expanded details.
- Terpene compact field for cannabis.
- Completeness and em-dash rendering.
- Full browser matrix and mobile parity.

A later PR must not narrow the website matrix or silently defer a required vendor. A source may remain blocked or empty, but its routes, fixtures, tests, and health evidence must exist.