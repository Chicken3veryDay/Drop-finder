# DropFinder catalog v4 shopper-data contract

## Purpose

Catalog v4 is the stable boundary between retrieval/classification and the
marketplace UI. The upstream v3 snapshot remains a rollback input. V4 applies
shopper-safe stock, identity, variant, price, potency, and provenance rules and
publishes a compact index plus lazy detail shards.

## Publication layout

| Path | Purpose |
|---|---|
| `data/catalog-v4/manifest.json` | Generation identity, counts, paths, and SHA-256 hashes |
| `data/catalog-v4/index.json` | Compact search/sort/filter payload used for the first render |
| `data/catalog-v4/details/NNN.json` | Lazy product detail shards selected by stable product ID |
| `data/catalog-v4/vendors.json` | Vendor favicon and age-gate profile records |
| `data/catalog-v4/rejections.json` | Stock/weight/price/URL exclusions with stable reason codes |

Every file in a generation carries the same 32-character `generation_id`.
The manifest hashes the exact UTF-8 bytes of every referenced file. Consumers
must reject mixed-generation or hash-mismatched files.

## Product identity

`product_id` is a stable SHA-256-derived identifier. Identity evidence is
ranked in this order:

1. Source product ID or product handle.
2. Canonical storefront product handle from the URL.
3. Canonical product URL.
4. Conservative vendor + canonical title fallback.

A canonical product groups all qualifying package sizes. Source titles remain
available in product details, while `strain_name` removes only recognized
flower, environment, marketing, and weight suffixes. The generator resolves
same-vendor duplicate canonical URLs by source authority, variant coverage,
field completeness, and freshness and records the decision in provenance.

## Variant contract

A variant is published only when all of these are true:

- Stock is explicitly true or an explicit source state normalizes to in stock.
- Weight is valid and normalizes to a positive gram amount.
- Current price is positive and finite.
- Product and variant URLs are public HTTP(S) URLs.

Unknown stock and sold-out variants are rejected from the shopper payload.
When every variant is rejected, the product disappears from v4. Common ounce
labels snap to shopper package weights: 1/8 = 3.5 g, 1/4 = 7 g, 1/2 = 14 g,
1 oz = 28 g, 2 oz = 56 g, and 4 oz = 112 g. The original source weight label
is preserved.

Duplicate source variants are resolved by completeness, explicit source
identity, and freshness. Only one selector entry is published per normalized
weight.

## Active variant selection

The UI may restrict variants by an inclusive weight range. Among eligible
in-stock variants, `select_active_variant` applies this deterministic order:

1. Lowest price per gram.
2. Lower total current price.
3. Lower gram weight.
4. Stable variant ID.

`default_variant_id` in the compact index is the result with no weight bounds.
Changing weight filters must rerun the same selection rule.

## Pricing

Each variant exposes:

- `current_price`
- `original_price`, only when strictly greater than current price
- `discount_percent = (original - current) / original * 100`
- `price_per_gram = current_price / grams`

Contradictory original prices are removed and identified by
`pricing_warning`. Price provenance retains raw current/original values,
source path, source type, collection timestamp, and confidence.

## Total THC

UI-facing potency is `Total THC`, never raw THCA. The formula is:

`delta9_thc + (thca * 0.877)`

When Delta-9 is explicitly reported as ND/non-detect, it normalizes to zero.
When THCA exists but Delta-9 is absent, the generator may publish a clearly
labeled `thca_only_estimate`. Impossible percentages are rejected. Product
details preserve raw THCA, raw Delta-9, any direct source Total THC, formula,
method, confidence, and field-level provenance. The compact index stores the
nearest whole-number display value without a decimal.

## Lineage, effects, environment, and reviews

`lineage` is exactly one of:

- `indica`
- `indica_leaning_hybrid`
- `hybrid`
- `sativa_leaning_hybrid`
- `sativa`
- `unknown`

Effects are source-exposed values only and are normalized/deduplicated without
inventing absent effects. Grow environment is normalized from explicit or
conservative source text to `indoor`, `outdoor`, `greenhouse`, or `unknown`.
Ratings publish only when both a valid 0–5 score and a positive integer review
count exist.

## Documents

Variant details accept public COA, terpene, combined, or unknown documents.
Documents can be scoped to a variant, normalized weight, batch, product, or
vendor. Variant/weight mappings are validated before publication. Unsafe URLs
and conflicting scopes are omitted.

## Rejection reason codes

Current stable reasons include:

- `out_of_stock_variant`
- `unknown_stock_variant`
- `invalid_or_missing_weight`
- `missing_or_invalid_current_price`
- `missing_or_invalid_product_url`
- `missing_product_identity_fields`

The rejection artifact is not intended for the browser UI. It exists for
operator diagnosis and regression tests.
