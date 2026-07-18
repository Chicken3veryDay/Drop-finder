# DropFinder multi-product production contract

## Status

This document defines the current supported type-aware marketplace contract. DropFinder supports four primary product types:

- `cannabis_flower`
- `cannabis_vape`
- `psilocybin_mushroom`
- `psilocybin_vape`

Every published record has exactly one supported `primary_type`. `type_tags` may contain more than one supported type only when explicit source evidence independently satisfies every tag. Unsupported categories are not relabeled into a supported category.

## Common product contract

Every admitted product and variant carries, where applicable:

- stable product and variant identities;
- vendor identity;
- canonical public product URL when outbound commerce is permitted;
- source product and variant identifiers;
- source and normalized display titles;
- `primary_type` and supported `type_tags`;
- current and original price evidence;
- explicit stock state;
- image URL when public;
- normalized quantity and unit for the primary type;
- a type-specific comparison metric;
- completeness score;
- field-level provenance and collection time;
- classification evidence;
- optional documents with product, variant, weight, lot, or batch scope.

Missing optional values remain `null` in published data and render as `—`. The pipeline must not invent quantities, potency, stock, provenance, or comparison values.

## Type contracts

### Cannabis flower

Required classification evidence is explicit THCA plus flower form, with non-flower forms excluded. Quantity is normalized in grams and the comparison metric is `price_per_gram`.

Compact and detail data may include lineage, total THC or THCA display, package variants, terpenes, effects, grow environment, potency provenance, images, and COA documents.

### Cannabis vape

Required classification evidence is explicit cannabis plus vape form. Publication requires explicit source volume in milliliters and a coherent `price_per_ml` comparison. Mass-only vape evidence is preserved for diagnostics but is not converted to milliliters without a documented density contract.

Compact and detail data may include device type, volume, puff count, terpenes, and COA documents. Device compatibility, rechargeable status, blend ingredients, and inferred cannabinoid summaries are not normalized fields.

### Psilocybin mushroom

Required classification evidence is explicit psilocybin plus mushroom form, excluding vape and Amanita signals. Quantity is normalized in grams and the comparison metric is `price_per_gram`.

Source claims and laboratory measurements remain separate. The normalized shopper publication does not expose outbound purchase links for controlled products.

### Psilocybin vape

Required classification evidence is explicit psilocybin plus vape form, excluding Amanita signals. Publication requires explicit milliliter volume and `price_per_ml`.

Source claims and laboratory measurements remain separate. The normalized shopper publication does not expose outbound purchase links for controlled products.

## Retired product type decision: cannabis edibles

`cannabis_edible` was formally retired from the v1 contract on July 18, 2026. The identifier is neither stable nor enabled, and the classifier, exports, UI selector, filters, comparison metric, and row contract are removed together.

The prior planning text described a category that the repository did not implement end to end. There was no accepted production contract for piece count, labeled active amount, active amount per piece, multiple active ingredients, `price_per_100mg`, completeness scoring, publication admission, generated artifacts, shopper cards, legal boundaries, or release acceptance. Keeping the type declared would falsely imply production support.

Edible-only products and mixed offers whose primary representation would require an edible contract remain unsupported. They are not classified as flower, vape, or mushroom products merely to retain them.

A future reintroduction requires:

1. a versioned taxonomy and publication schema;
2. explicit product-level evidence rules;
3. quantity and active-amount normalization;
4. a documented comparison metric and completeness model;
5. legal, privacy, and outbound-link review;
6. generated-data migration and rollback rules;
7. UI selector, cards, filters, sorting, and accessibility acceptance;
8. negative classification and cross-browser tests;
9. a production deployment receipt.

The retired identifier must not be silently reused with different semantics.

## Controlled-product boundary

DropFinder may index public informational metadata for psilocybin products, but the normalized shopper publication must not expose outbound purchase links for controlled psilocybin products. Source URLs may remain in restricted operator provenance when required for reproducibility.

No age gate, jurisdiction gate, dosage advice, or promotional safety badge is introduced by this contract.

## Completeness and evidence

Completeness is calculated per supported primary type. It measures field presence, not product quality, safety, authenticity, potency, or vendor trustworthiness.

Evidence rules:

- product-level evidence is preferred over listing-card text;
- source claims and laboratory values are labeled separately;
- document-derived fields retain document, batch, lot, weight, and variant scope;
- incompatible units are not combined;
- stale, blocked, rejected, and incomplete states remain observable;
- generated artifacts fail closed when required evidence or strict JSON compatibility is missing.

## Publication and rollback

Publication must produce a complete, hash-consistent generation containing manifests, compact indexes, detail shards, source status, runtime status, and deployment evidence. Zero-product or zero-active-source snapshots must not replace a healthy generation without an explicit emergency policy.

Rollback restores one complete prior generation. A rollback must not combine manifests, indexes, shards, assets, or service-worker state from different generations or deployment scopes.
