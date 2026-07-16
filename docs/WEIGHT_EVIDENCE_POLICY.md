# Catalog weight evidence policy

Shopper-facing package weight and price-per-gram values must come from explicit source evidence. Arithmetic consistency is not enough: a price divided by an inferred or contaminated weight still produces a misleading comparison value.

## Accepted evidence

- Explicit source labels such as `3.5 g`, `1/8 oz`, `1 oz`, or `two ounces`.
- A normalized `weight_grams` value supplied by an adapter that owns the source-field mapping.
- A legacy numeric `grams` value only when the same record contains an explicit label that normalizes to the same commercial weight.

## Rejected evidence

- Bare merchandising or taxonomy numbers such as `Tier 1`, `Type 1`, or `4 pack`.
- Digits embedded in potency or other decimal text, such as `24.1%`.
- Pound labels while pound-package normalization is unsupported. These must fail closed rather than being interpreted as fractional ounces.
- Numeric legacy values whose source label is absent or contradicts the normalized weight.

Rows without attributable weight evidence are excluded from catalog-v4 weight and price-per-gram publication. This is preferable to guessing a package size and silently changing default marketplace ranking or filters.

When weight parsing changes, validate the producer, catalog-v4 normalization, builder rejection behavior, and a migration of the current committed catalog input before publication.
