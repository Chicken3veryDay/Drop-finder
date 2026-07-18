# DropFinder UI performance, documents, and PWA platform

## Scope and public interfaces

This isolated workstream supplies headless platform capabilities for issue #8 through issue #5's versioned registration seam. It does not own marketplace markup, catalog generation, seller research, or global design tokens.

- `CatalogGenerationClient`: manifest-first atomic preparation, schema/generation/hash validation, service-worker activation coordination before publication, abortable bounded fetches, concurrent-request deduplication, persistent last-complete fallback, and bounded detail LRU.
- `MarketplaceQueryEngine`: one-time compact-index transfer to a dedicated worker, deterministic search/filter/sort, stable pagination identity, stale-response rejection, one bounded worker restart, and an honest limited synchronous fallback.
- `VirtualMarketplaceAdapter`: variable-height measurement, bounded rendered windows and retained pages, duplicate suppression, stable scroll anchors, focus retention, and complete-result accessibility counts.
- `DocumentViewerCapability`: real lazy PDF.js rendering with a dedicated worker, images, external-only HTML, unsupported fallbacks, bounded bytes/pages/scale, render cancellation, resource release, focus trapping/restoration, and scroll locking.
- `PwaGenerationCoordinator`: typed service-worker registration, normalized generation status, explicit activation acknowledgement, bounded activation failure, and quiet complete-generation updates without forced reloads.
- `createSyntheticCatalog`: deterministic 1,000/10,000/50,000-product fixtures with four variants and mixed optional detail/document metadata.

All registration descriptors use `PLATFORM_CONTRACT_VERSION = 1`. Catalog manifests currently require schema version 4.

## Catalog and generation contract

A v4 manifest contains an immutable `generation_id`, compact index descriptor, declared byte counts and SHA-256 hashes, plus optional vendor and detail descriptors. Index, vendor, detail, and document metadata must agree on that generation. The client prepares a complete candidate without replacing the current generation. On a service-worker-controlled page, it then waits for the worker to acknowledge that exact generation as active before publishing the candidate. On an uncontrolled first visit, it may publish directly because no worker intercepts detail requests. Failed, incomplete, stale, aborted, or timed-out activation leaves the last complete active generation intact and returns a typed recoverable error.

The browser cache stores only the last validated complete generation. Missing, malformed, oversized, aborted, hash-mismatched, and generation-mismatched assets fail with concise typed errors. Detail requests are deduplicated and capped at 64 retained shards by default.

## Query semantics

Search covers vendor and strain only. Supported lineages are `indica`, `indica_hybrid`, `hybrid`, `sativa_hybrid`, `sativa`, and `unknown`. Supported sorts are the exact marketplace set: price, price per gram, Total THC, strain name, and vendor name in both directions.

The active variant within selected bounds is chosen by lowest price per gram, then lower total price, lower weight, and stable variant ID. Product and variant IDs provide deterministic final tie-breaks. A stable `queryKey` excludes page offset and request version so bounded endless pages from the same filter/sort can be combined without accepting stale pages from another query.

## PWA consistency

`cloud_pages/app-shell.json` provides relative application-shell metadata. The service worker:

- caches shell metadata and relative assets separately from generated data;
- prepares v4 manifest/index/vendor data in a generation-specific cache;
- supports the current legacy `catalog.json` and `status.json` pair atomically during migration;
- automatically activates only the first complete generation;
- announces later complete generations and waits for explicit application activation;
- keeps the active and one prior complete generation until replacement verification;
- rejects cross-generation detail shards;
- demand-caches at most 96 detail shards and 12 explicitly opened documents;
- refuses oversized, opaque, private, cookie-bearing, or `no-store` document responses;
- avoids install-time document precaching and forced reload loops.

The catalog client and PWA coordinator complete one activation handshake for every controlled-page generation switch. The coordinator subscribes before requesting status, normalizes the worker's persisted active identity, requests activation for the exact prepared generation, and waits for `generation-active`. `generation-error`, abort, registration failure with an existing controller, and activation timeout reject the refresh instead of exposing mixed-generation rows. The current catalog stays usable until the replacement acknowledgement arrives.

The manifest uses shopper marketplace wording, relative `start_url`/`scope`, dark-only colors, and no source-health/dashboard language.

## Document security and limits

`pdfjs-dist` is pinned to `6.1.200`. `pdfjs-loader.js` imports PDF.js only on first PDF open and configures the separately emitted PDF worker. The default limits are 20 MiB, 80 pages, scale 0.5 to 3, and device pixel ratio 2. Closing or replacing a document aborts network work, cancels rendering, destroys the PDF loading task, releases page resources, revokes image object URLs, unlocks scrolling, and restores invoking-control focus.

Arbitrary seller HTML is never embedded. It is external-only. Unsupported, encrypted, malformed, oversized, unavailable, or blocked documents expose one concise original-document fallback. No proxy or analytics service receives document bytes.

## Repeatable validation

From `web/`:

```bash
npm ci
npm run validate
npm run test:e2e:install
npm run test:e2e
```

`npm run validate` executes syntax/type checks, unit/resilience tests, deterministic performance fixtures, a Vite production build, and chunk analysis. The current environment-qualified local run on Node 22/Linux passed with 11 maximum rendered rows at every size. Representative p95 results were:

| Products | Combined query | Rapid typing | All sorts | Retained heap |
|---:|---:|---:|---:|---:|
| 1,000 | 0.48 ms | 3.05 ms | 2.79 ms | 2.15 MiB |
| 10,000 | 2.28 ms | 18.22 ms | 16.37 ms | 19.43 MiB |
| 50,000 | 12.11 ms | 155.48 ms | 141.00 ms | 85.84 MiB |

CI safety ceilings remain 100 ms at 10,000 products, 250 ms at 50,000 products, and 20 rendered rows. Parse time, fixture generation, scrolling-window work, expansion, catalog activation, detail first/cache-hit latency, and document-controller open time are also recorded. These Node compute measurements are not misrepresented as browser paint or frame timing.

The production build emits a roughly 35 KiB initial platform entry and separate lazy PDF.js chunks. Chunk analysis fails if PDF.js enters the initial marketplace entry or if the PDF worker is absent.

## Browser, accessibility, and resilience evidence

The self-contained Playwright harness uses the real worker, virtual adapter, pinned two-page PDF fixture, service worker, and headless document controller. It runs Chromium, Firefox, WebKit, and a mobile Chromium profile for:

- bounded endless scrolling over 10,000 products;
- rapid search cancellation, exact sort, and weight changes;
- expansion/collapse focus and scroll-anchor preservation;
- real two-page PDF render, navigation, zoom, Escape close, and focus restoration;
- unsupported-document fallback;
- quiet service-worker updates without reload;
- offline reload after complete shell caching;
- axe-core scans of the shell, marketplace feed, and document dialog.

The managed local container blocks local URLs in its preinstalled Chromium and cannot resolve Playwright's browser CDN, so local browser execution is recorded as unavailable rather than passed. GitHub Actions installs the official browser binaries and runs the complete suite on the exact pushed commit.
