# DropFinder UI Rewrite Contract

Status: foundation contract for issues #5 through #9  
Frontend API version: `1.0.0`  
Catalog schema version: `1.0.0`

## Product direction

DropFinder is a dark-only, restrained, dense marketplace for buyers who already understand basic cannabis terminology. Search and results begin near the top of the page. The interface uses deliberate whitespace to separate groups, compact controls where scanning benefits, and stable alignment for comparison.

The user-facing vocabulary is fixed:

| Internal or legacy term | User-facing term |
| --- | --- |
| Product Name | Strain Name |
| Strain Type | Lineage |
| THCA | Total THC |

Total THC is displayed as a rounded whole percent. Raw THCA and delta-9 THC values remain available only in typed internal data for calculation, provenance, validation, and later document work.

The following are intentionally absent: light mode, theme switching, Settings, Vendors, Favorites, Comparisons, scraping controls, gradients, glass effects, giant cards, hero copy, marketing banners, AI summaries, editorial layouts, terminal styling, security-operations styling, filler statistics, source-health drawers, refresh buttons, tutorial prose, and persistent explanatory status copy.

## Build and publication contract

The source application lives in `web/` and is built with React, TypeScript, and Vite. It publishes into the existing `cloud_pages/` tree.

- `base` is `./`; generated URLs must remain relative for GitHub Pages and raw.githack branch subpaths.
- Hashed JavaScript and CSS are emitted under `cloud_pages/assets/`.
- Vite runs with `emptyOutDir: false`.
- `web/scripts/build.mjs` snapshots `cloud_pages/data/`, `manifest.webmanifest`, `icon.svg`, and `sw.js`, builds the app, and fails if any protected file changes.
- `web/scripts/verify-publication.mjs` verifies the catalog/status/runtime files, PWA files, generated index, relative paths, and hashed assets.
- The existing Python retrieval, classification, admission, atomic `gh-pages` publication, verification, and rollback sequence remains authoritative.
- The frontend requires no credentials, application server, or external hosting service.

Deterministic commands, run from `web/`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run verify:publication
```

## Feature module registration

Sibling workstreams add modules beneath `web/src/features/<feature-id>/index.ts` or `index.tsx`. They do not edit foundation registry files. Vite discovers modules at build time through `import.meta.glob`.

A module exports either the feature object as `default` or as a named `feature` export. Use `defineFeature` so TypeScript checks the contract.

```tsx
import { defineFeature, FEATURE_API_VERSION } from "../../app/featureContract";
import { MarketplaceSurface } from "./MarketplaceSurface";

export default defineFeature({
  apiVersion: FEATURE_API_VERSION,
  id: "marketplace.catalog",
  kind: "marketplace",
  order: 100,
  capabilities: ["marketplace.surface"],
  slots: {
    marketplaceSurface: MarketplaceSurface,
  },
});
```

### Module fields

- `apiVersion`: exactly `1.0.0`.
- `id`: stable lowercase identifier using letters, digits, dots, or dashes.
- `kind`: `marketplace` or `enhancer`.
- `order`: non-negative integer. Modules sort by order and then ID.
- `capabilities`: unique declarations from the typed capability list.
- `slots`: renderable React components for supported shell mount points.

Supported capabilities:

- `marketplace.surface`
- `marketplace.search`
- `marketplace.filters`
- `marketplace.result-header`
- `platform.document-overlay`
- `platform.virtualization`
- `platform.pwa-status`
- `platform.mobile-rendering`

Supported slots:

| Slot | Expected owner | Purpose |
| --- | --- | --- |
| `search` | primary marketplace | Optional replacement for the foundation search field |
| `filters` | primary marketplace | Horizontal marketplace filter controls |
| `resultHeader` | primary marketplace | Result count and compact list header |
| `marketplaceSurface` | primary marketplace | Required primary result surface |
| `overlay` | enhancer | Document or platform overlay mounted against the portal host |

A marketplace module must declare and implement `marketplace.surface`. A component supplied for a capability-bound slot must declare the matching capability.

The registry fails closed:

- malformed modules are rejected;
- every copy of a duplicated ID is rejected;
- if multiple primary marketplace modules exist, all primary modules are rejected;
- a slot with multiple providers is left unmounted;
- unsupported capabilities and capability/slot mismatches are rejected.

The foundation renders no blank dashboard, placeholder card, or filler copy when a feature is absent. Development builds may show one concise unavailable-module error. Production remains structurally empty until the primary marketplace module is present.

## Shared catalog contract

Canonical types and validators are exported from `web/src/contracts/index.ts`.

### Manifest and paging

`CatalogManifest` contains:

- schema and catalog versions;
- generation time;
- catalog index URL, digest, generation time, page count, and product count;
- deterministic page metadata with IDs, URLs, digests, counts, and first/last product keys.

`CatalogPage` binds page metadata to validated marketplace products.

### Marketplace product

`MarketplaceProduct` groups one canonical product/strain identity under one vendor. It contains:

- vendor product ID, canonical strain ID, and canonical product ID;
- vendor ID/name, favicon, age-gate classification, and evidence;
- Strain Name and six-value Lineage;
- at least one `InStockVariant`;
- calculated Total THC and internal raw cannabinoid values;
- rating and review count;
- effects;
- grow environment;
- COA and terpene document mappings;
- evidence and provenance.

Lineage values are:

- `indica`
- `indica-leaning-hybrid`
- `hybrid`
- `sativa-leaning-hybrid`
- `sativa`
- `unknown`

Grow environment values are `indoor`, `outdoor`, `greenhouse`, and `unknown`.

### In-stock boundary

The frontend variant type only permits:

```ts
stock: {
  state: "in_stock";
  available: true;
  observedAt: string;
}
```

Runtime validation rejects any other stock state. Out-of-stock data can exist upstream, but it cannot enter the frontend-visible product contract by accident.

Every in-stock variant includes weight, current price, optional original price, optional discount percent, price per gram, product URL, optional image URL, document IDs, batch IDs, explicit stock evidence, and field evidence. Money uses integer cents and `USD` to avoid display drift.

### Total THC

`TotalThcMeasurement` supports:

- a source-reported Total THC value;
- a calculated value using `thca * 0.877 + delta9_thc`;
- unavailable data with explicit nulls.

`roundedDisplayPercent` must equal `Math.round(calculatedPercent)` when a calculated value exists. Raw THCA, delta-9 THC, reported Total THC, method, formula, and provenance remain internal and typed.

### Documents

`ProductDocumentRecord` supports `coa` and `terpene` documents. Every record maps to a vendor, product, zero or more variants, zero or more batches, publication time, and evidence. Document rendering and PDF parsing belong to later workstreams.

## Design system contract

The design system is CSS-variable based. It does not depend on a themed component library.

Tokens cover:

- dark neutral canvas, surfaces, borders, and text hierarchy;
- focus, error, and subdued states;
- resting and hover tints for all six Lineage values;
- responsive type and spacing scales;
- compact control and row dimensions;
- tabular numerals;
- reduced motion;
- increased contrast and visible keyboard focus.

Rows remain neutral by default. A Lineage tint is restrained at rest and clearer on hover. No token introduces gradients or decorative shadows.

Reusable primitives are deliberately limited to visually hidden text, a visible-focus icon button, an accessible field wrapper, and a modal portal host.

## Shell and keyboard contract

The shell contains:

- a lowercase `dropfinder` wordmark;
- the active `Marketplace` section;
- a full-width search region;
- a horizontal filter mount;
- a result summary/header mount;
- a marketplace surface mount;
- an overlay portal host.

Pressing `/` focuses search when the current target is not editable. Pressing `Escape` clears a non-empty focused search; pressing it again leaves the field. Shortcut hints remain visually hidden because the interface does not need permanent instruction copy.

## Parallel ownership

Issue #5 owns foundation and contract files. Sibling issues should create isolate feature directories and import the stable contracts rather than changing foundation files.

- Marketplace rows and behavior: add a primary marketplace feature.
- Vendor research and catalog enrichment: produce data matching the shared contracts.
- COA and terpene viewing: add a document overlay enhancer.
- Virtualization: add an enhancer capability without replacing product semantics.
- Mobile rendering: add a mobile enhancer or module-owned responsive implementation after desktop behavior is complete.

No sibling should add Settings, Favorites, Vendors, Comparisons, scraping/operator UI, or reintroduce legacy terminology.
