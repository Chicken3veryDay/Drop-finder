# DropFinder marketplace feature

This directory is the isolated Issue #8 marketplace package. It owns shopper-facing search, filters, sorting, compact rows, inline expansion, responsive mobile rendering, and document-action wiring. It does not own catalog generation, vendor research, application-shell tokens, virtualization, PWA behavior, or PDF rendering.

## Public entry points

- `MarketplaceFeature`: React primary surface.
- `marketplaceFeatureModule`: issue #5 feature-registration object (`id: marketplace`, `kind: primary`, version 1).
- `queryMarketplace`: deterministic feature-local fallback query implementation.
- `MarketplaceFeatureProps`: integration contract for catalog data, lazy details, platform query execution, document viewing, and virtualization.

## Sibling contracts

### Issue #5 foundation

The module expects React and the shared dark design tokens. Every CSS variable has a dark local fallback so this branch can be reviewed independently. The final integrator should register the default export through the foundation feature registry without editing this package.

### Issue #6 catalog v4

Map the compact catalog index into `MarketplaceProduct[]`. Pass detail shards through `detailsByProductId` or `loadDetail`. Only explicitly in-stock variants are accepted. The UI does not rewrite strain identity, calculate Total THC, infer lineage/effects, or repair pricing.

### Issue #7 vendor/document data

Map weight/variant-specific COA and terpene records directly onto each `MarketplaceVariant`. Document identity is never guessed by display order.

### Issue #9 platform

Pass the platform `MarketplaceQueryCapability`, `DocumentViewerCapability`, and `VirtualMarketplaceAdapter` through props. The feature-local document overlay is a safe fallback: images render directly, while PDF/HTML/unsupported documents offer the original public source. Full PDF navigation/zoom belongs to issue #9.

## Behavior guarantees

- Search matches vendor and strain name only.
- Filters appear in the required order and update immediately.
- Sort options are limited to the exact eight shopper sorts.
- Active variant is selected within the weight range by lowest PPG, then lower total price, lower weight, and stable variant ID.
- Price, original price, discount, PPG, product URL, image, COA, and terpene actions all derive from one selected variant.
- Invalid or non-positive price/weight/PPG records are not rendered.
- Potency is rounded to a whole percent and never exposes the raw laboratory field name.
- Only one row is expanded at a time, and expansion closes when filtering removes the product.
- Desktop uses a continuous aligned row list. Mobile switches to a purpose-built two-line layout instead of horizontally scrolling the desktop grid.
- `/` focuses search. Escape clears search first, then blurs it. Enter and Space toggle rows.
- Reduced motion, forced colors, visible focus, result announcements, focus restoration, and modal focus trapping are included.

## Local validation

The package deliberately avoids owning the root frontend lockfile. In a checkout with Node and TypeScript available:

```bash
tsc -p web/src/features/marketplace/tsconfig.json
rm -rf .tmp-marketplace-tests
mkdir -p .tmp-marketplace-tests

tsc \
  --target ES2022 \
  --module NodeNext \
  --moduleResolution NodeNext \
  --strict \
  --skipLibCheck \
  --outDir .tmp-marketplace-tests \
  web/src/features/marketplace/test/node-shim.d.ts \
  web/src/features/marketplace/marketplace-core.ts \
  web/src/features/marketplace/test/fixtures.ts \
  web/src/features/marketplace/test/marketplace-core.test.ts

node --test .tmp-marketplace-tests/test/marketplace-core.test.js
```

Browser component, visual-regression, mobile Safari/Chrome, and real document-capability tests must run after the issue #5 and #9 branches are integrated. This isolated branch intentionally does not take ownership of their React/Vite/Playwright lockfile or platform runtime, so those checks are not represented as passed here.
