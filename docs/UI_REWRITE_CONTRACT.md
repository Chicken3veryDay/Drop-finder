# DropFinder UI Rewrite Contract

Status: foundation contract for issues #5 through #9  
Frontend API version: `1.0.0`  
Runtime capability contract: versioned per capability  
Catalog contract version: `1.0.0`

## Product direction

DropFinder is a dark-only, restrained, dense marketplace for buyers who already understand basic cannabis terminology. Search and results begin near the top of the page. The interface uses deliberate whitespace to separate groups, compact controls where scanning benefits, and stable alignment for comparison.

The user-facing vocabulary is fixed:

| Internal or legacy term | User-facing term |
| --- | --- |
| Product Name | Strain Name |
| Strain Type | Lineage |
| THCA | Total THC |

Total THC is displayed as a rounded whole percent. Raw THCA and delta-9 THC values remain internal for calculation, provenance, and validation.

The following are intentionally absent: light mode, theme switching, Settings, Vendors, Favorites, Comparisons, scraping controls, gradients, glass effects, giant cards, hero copy, marketing banners, AI summaries, editorial layouts, terminal styling, security-operations styling, filler statistics, source-health drawers, refresh buttons, tutorial prose, and persistent explanatory status copy.

## Build and publication contract

The source application lives in `web/` and publishes into the existing `cloud_pages/` tree.

- Vite `base` is `./` so GitHub Pages and raw.githack branch subpaths remain valid.
- Hashed JavaScript and CSS are emitted under `cloud_pages/assets/`.
- Vite uses `emptyOutDir: false`.
- `web/scripts/build.mjs` snapshots `cloud_pages/data/`, `manifest.webmanifest`, `icon.svg`, and `sw.js`, then fails if the frontend build changes any protected file.
- `web/scripts/verify-publication.mjs` verifies catalog/status/runtime data, PWA files, the generated index, relative paths, and hashed assets.
- Existing Python retrieval, admission, atomic `gh-pages` publication, verification, and rollback remain authoritative.
- The frontend requires no credentials, server, or external hosting service.

Deterministic commands from `web/`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run verify:publication
```

## Feature discovery

Sibling workstreams add isolated files beneath `web/src/features/<feature-id>/`. Vite discovers:

- `index.ts`, `index.tsx`, `index.js`, `index.jsx`, or `index.mjs`;
- `register-*.ts`, `register-*.tsx`, `register-*.js`, `register-*.jsx`, or `register-*.mjs`.

Registrar-only files are not treated as malformed feature modules.

## Canonical feature module

A canonical module exports the feature object as `default` or as named `feature` and should use `defineFeature`.

```tsx
import { defineFeature, FEATURE_API_VERSION } from "../../app/featureContract";
import { MarketplaceSurface } from "./MarketplaceSurface";

export default defineFeature({
  apiVersion: FEATURE_API_VERSION,
  id: "marketplace.catalog",
  kind: "marketplace",
  order: 100,
  capabilities: ["marketplace.surface"],
  slots: { marketplaceSurface: MarketplaceSurface },
});
```

Module fields:

- `apiVersion`: exactly `1.0.0`.
- `id`: stable lowercase dotted or dashed identifier.
- `kind`: `marketplace` or `enhancer`.
- `order`: non-negative integer; modules sort by order and then ID.
- `capabilities`: unique declarations from the typed list.
- `slots`: renderable React components for supported shell mount points.

Supported marketplace capabilities are `marketplace.root`, `marketplace.surface`, `marketplace.search`, `marketplace.filters`, and `marketplace.result-header`.

Supported platform declarations are `platform.catalog`, `platform.query`, `platform.documents`, `platform.document-overlay`, `platform.virtualization`, `platform.pwa`, `platform.pwa-status`, and `platform.mobile-rendering`.

Supported slots:

| Slot | Purpose |
| --- | --- |
| `marketplaceRoot` | Whole-marketplace compatibility surface that owns search, filters, summary, and results |
| `search` | Optional replacement for the foundation search field |
| `filters` | Horizontal marketplace filters |
| `resultHeader` | Result count and compact list header |
| `marketplaceSurface` | Primary result surface in the decomposed shell |
| `overlay` | Document or platform overlay mounted against the portal host |

A primary marketplace must implement either `marketplace.root` or `marketplace.surface`. A root provider may not also supply decomposed marketplace slots because that would duplicate search and filters.

Every slot receives the read-only runtime capability registry through a `capabilities` prop.

The module registry fails closed:

- malformed modules are rejected;
- all copies of a duplicated ID are rejected;
- multiple primary marketplaces are all rejected;
- a slot with multiple providers is left unmounted;
- unsupported declarations and capability/slot mismatches are rejected.

## Issue #8 primary-v1 compatibility

The completed issue #8 branch exports this isolated shape:

```ts
{
  id: "marketplace",
  kind: "primary",
  version: 1,
  mount: MarketplaceFeature,
  capabilities: ["desktop", "mobile", "documents", "keyboard"]
}
```

The foundation adapts that exact shape to `marketplace.root`. When a root is mounted, the foundation does not render its own search, filters, result header, or result surface, preventing duplicate controls.

The compatibility wrapper passes:

- `products: []` by default;
- the read-only capability registry as `capabilities`;
- any version-1 object registered as `marketplace.props`, which overrides the empty data defaults.

A final integrator should register `marketplace.props` through a small adapter that maps issue #6 catalog output and issue #9 platform capabilities into issue #8's `MarketplaceFeatureProps`. The foundation intentionally does not guess across incompatible async/sync interfaces.

## Runtime capability registration

The preferred registrar export is `registerFeatureCapabilities(registry)`. The issue #9 compatibility export `registerPlatformCapabilities(registry)` is also supported.

The target implements:

```ts
interface CapabilityRegistrationTarget {
  registerCapability<T>(
    name: string,
    descriptor: { contractVersion: number | string; instance: T },
  ): boolean;
}
```

Canonical names currently reserved for integration are:

- `marketplace.props`
- `platform.catalog`
- `platform.query`
- `platform.virtualization`
- `platform.documents`
- `platform.pwa`

Consumers use `getCapability(name, expectedVersion)`. A version mismatch returns `undefined`. Duplicate providers disable the capability entirely rather than allowing import order to choose a winner. Malformed or throwing registrars become diagnostics and do not crash the shell. Registrars must finish synchronously during build-time discovery.

## Shared catalog contract

Canonical types and validators are exported from `web/src/contracts/index.ts`.

`CatalogManifest` contains schema/catalog versions, generation time, index metadata, and deterministic page metadata. `CatalogPage` binds page metadata to validated marketplace products.

`MarketplaceProduct` groups one canonical product/strain under one vendor and contains vendor identity/evidence, Strain Name, six-value Lineage, one or more in-stock variants, calculated Total THC with raw internal values, rating/review count, effects, grow environment, documents, and evidence.

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

Runtime validation rejects every other stock state. Every variant includes weight, current/original pricing, optional discount, price per gram, product/image URLs, document and batch IDs, stock evidence, and field evidence. Money uses integer cents and `USD`.

### Total THC

`TotalThcMeasurement` supports a source-reported Total THC value, a calculation using `thca * 0.877 + delta9_thc`, or explicit unavailable data. `roundedDisplayPercent` must equal `Math.round(calculatedPercent)` when a calculated value exists.

### Documents

`ProductDocumentRecord` supports `coa` and `terpene` records mapped to vendor, product, variants, batches, publication time, and evidence. Rendering and parsing remain sibling responsibilities.

## Design system contract

The CSS-variable system covers dark neutral surfaces and text hierarchy, focus/error/subdued states, six resting/hover Lineage tints, responsive type and spacing, compact control/row dimensions, tabular numerals, reduced motion, increased contrast, and visible keyboard focus. It introduces no gradients or decorative shadows.

Reusable primitives remain limited to visually hidden text, a visible-focus icon button, an accessible field wrapper, and a modal portal host.

## Shell and keyboard contract

The decomposed shell contains the lowercase `dropfinder` wordmark, `Marketplace`, full-width search, filters, result header, result surface, and overlay host. `/` focuses foundation search and Escape clears then leaves it.

A composite `marketplaceRoot` owns those interactions itself. The foundation disables its duplicate global search shortcut in that mode.

## Parallel ownership

Issue #5 owns foundation and contract files. Siblings should add isolated feature/platform files and use these seams rather than modifying foundation files.

- Issue #6 produces shopper data and a `marketplace.props` adapter input.
- Issue #7 produces vendor/document evidence.
- Issue #8 supplies the primary marketplace root.
- Issue #9 registers platform capabilities.

No sibling should add Settings, Favorites, Vendors, Comparisons, scraping/operator UI, or legacy user-facing terminology.
