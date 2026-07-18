# Vape quantity publication contract

DropFinder publishes cannabis and psilocybin vape products only when the source exposes a coherent volume quantity in milliliters.

## Supported representation

A publishable vape row requires:

- explicit product-level vape classification evidence;
- `quantity_unit` equal to `ml`;
- a finite positive `volume_ml`;
- `comparison_metric` equal to `price_per_ml`;
- a finite positive `comparison_price` derived from the published price and volume.

When both mass and volume appear in source evidence, explicit volume is the publication quantity. The original source text and provenance remain available for diagnostics.

## Unsupported representation

A mass-only vape label is not converted from grams to milliliters. DropFinder has no accepted density contract that would make that conversion reliable across oils, devices, additives, and source conventions.

Mass-only rows preserve their explicit gram evidence during normalization and are rejected from publication with:

`unsupported_vape_mass_quantity`

Other stable rejection reasons include:

- `missing_vape_volume`
- `missing_vape_comparison_price`
- `inconsistent_vape_comparison_price`

## Release acceptance

Code-level tests are necessary but not sufficient to close a publication-integrity issue. The generated release artifacts must also demonstrate that unsupported mass-only rows are absent or carry the documented rejection reason, and that every published vape row has a coherent milliliter quantity and price-per-milliliter comparison.

A future mixed-unit representation requires a versioned schema, documented source evidence and density semantics, UI support, migration and rollback rules, and regenerated acceptance evidence.
