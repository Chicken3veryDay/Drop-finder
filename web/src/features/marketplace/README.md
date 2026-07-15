# DropFinder marketplace feature

This directory owns the shopper-facing marketplace feature: search, filters, sorting, compact rows, inline expansion, responsive presentation, and document-action wiring. It does not own catalog generation, vendor research, application-shell tokens, virtualization, PWA behavior, or PDF rendering.

## Public entry points

- `MarketplaceFeature`: React primary surface.
- `marketplaceFeatureModule`: feature-registration object (`id: marketplace`, `kind: primary`, version 1).
- `queryMarketplace`: deterministic feature-local fallback query implementation.
- `MarketplaceFeatureProps`: integration contract for catalog data, lazy details, platform query execution, document viewing, and virtualization.

## Sibling contracts

### Foundation

The module expects React and the shared dark design tokens. Every CSS variable has a dark local fallback so the feature can be reviewed independently. The feature is registered through the foundation feature registry.

### Catalog v4

Map the compact catalog index into `MarketplaceProduct[]`. Pass detail shards through `detailsByProductId` or `loadDetail`. Only explicitly in-stock variants are accepted. The UI does not rewrite strain identity, calculate Total THC, infer lineage/effects, or repair pricing.

### Vendor and document data

Map weight/variant-specific COA and terpene records directly onto each `MarketplaceVariant`. Document identity is never guessed by display order.

### Platform

Pass the platform `MarketplaceQueryCapability`, `DocumentViewerCapability`, and `VirtualMarketplaceAdapter` through props. The feature-local document overlay is a safe fallback: images render directly, while PDF/HTML/unsupported documents offer the original public source. Full PDF navigation and zoom belong to the platform capability.

## Behavior guarantees

- Search matches vendor and strain name only.
- Filters appear in the required order and update immediately.
- Sort options are limited to the exact eight shopper sorts.
- Active variant is selected within the weight range by lowest PPG, then lower total price, lower weight, and stable variant ID.
- Price, original price, discount, PPG, product URL, image, COA, and terpene actions all derive from one selected variant.
- Invalid or non-positive price/weight/PPG records are not rendered.
- Potency is rounded to a whole percent and never exposes the raw laboratory field name.
- Only one row is expanded at a time, and expansion closes when filtering removes the product.
- Desktop and mobile use the same row, filter, detail, and state components. Responsive CSS reflows the existing desktop fields without creating a separate mobile product surface.
- Mobile preserves all eight desktop row fields, their labels, ordering, formatting, and actions.
- `/` focuses search. Escape clears search first, then blurs it. Enter and Space toggle rows.
- Reduced motion, forced colors, visible focus, result announcements, focus restoration, and modal focus trapping are included.

The complete responsive contract and acceptance matrix are documented in [`docs/MOBILE_DESKTOP_PARITY_BUILD_SPEC.md`](../../../../docs/MOBILE_DESKTOP_PARITY_BUILD_SPEC.md).

## Local validation

From `web/` in a checkout with Node 22 or newer:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run build
```

The Playwright matrix includes desktop Chromium, Firefox, WebKit, Pixel 7 Chromium, and iPhone WebKit. The integrated mobile test checks desktop-field parity, filter availability, inline expansion, touch-target sizing, accessibility, bounded virtualization, and document-level overflow.
