# DropFinder UI performance, documents, and PWA platform

## Scope

This workstream provides headless platform capabilities for the issue #8 marketplace and the issue #5 capability registry. It deliberately does not own marketplace markup, shell styling, catalog generation, or vendor/document discovery.

Public modules:

- `CatalogGenerationClient`: atomic manifest/index activation, generation consistency, request cancellation and deduplication, bounded retries, bounded detail-shard LRU, and last-complete cache fallback.
- `MarketplaceQueryEngine`: versioned worker protocol, deterministic filters/sorts, active-variant selection, stale-result rejection, and a limited synchronous fallback.
- `VirtualMarketplaceAdapter`: variable-height measurement, anchor preservation, bounded windows, page deduplication, focus retention, and complete-result accessibility counts.
- `DocumentViewerCapability`: lazy PDF.js loading through an injected loader, bounded fetch/page/render state, cancellation, focus trap, scroll lock, focus restoration, images, external HTML, and original-link fallback states.
- `PwaGenerationCoordinator`: typed service-worker registration and complete-generation update events without forced reloads.

All public contracts use `PLATFORM_CONTRACT_VERSION = 1`. Catalog data currently expects schema version 4.

## Catalog publication contract

A manifest must include:

```json
{
  "schema_version": 4,
  "generation_id": "immutable-generation-id",
  "index": {"url": "catalog-index.json", "bytes": 1234, "sha256": "..."},
  "details": {
    "product-id": {"url": "details/00.json", "bytes": 1234, "sha256": "..."}
  }
}
```

Every index/detail/vendor response must carry the same `generation_id` in its JSON envelope. The service worker additionally honors `X-DropFinder-Generation`. A mixed generation returns an explicit failure rather than silently combining snapshots.

The static service worker keeps immutable shell assets separately from generated data. A new generation is prepared in a new cache, validated as complete, announced with `generation-ready`, and activated only after an application message. One prior complete generation remains until replacement activation. Detail shards are demand-cached and capped. Documents are cached only after explicit opening and only below 20 MiB.

## Query semantics

Search is limited to vendor and strain. Supported lineage values are `indica`, `indica_hybrid`, `hybrid`, `sativa_hybrid`, `sativa`, and `unknown`.

Supported sorts are:

- `lowest_price`, `highest_price`
- `lowest_ppg`, `highest_ppg`
- `highest_total_thc`, `lowest_total_thc`
- `strain_az`, `strain_za`
- `vendor_az`, `vendor_za`

The active variant is selected within weight/price/PPG bounds by lowest PPG, then lower total price, lower weight, and stable variant ID. Product ID and variant ID provide final stable sort tie-breaks. No fuzzy matching, recommendation, hidden score, or relevance ranking is present.

## Performance budgets

Run from `web/`:

```bash
npm ci
npm run validate
```

The deterministic benchmark builds 1,000, 10,000, and 50,000 product compact indexes with four variants each. After warmup, seven samples are measured. CI safety ceilings are 100 ms at 1,000 and 10,000 rows and 250 ms at 50,000 rows for the combined query fixture. The virtualized window must remain at or below 20 rows for the benchmark viewport.

These are environment-qualified Node compute measurements, not claims about integrated paint or scrolling. Integrated browser checks belong to the Playwright suite after issues #5 and #8 are combined. The branch records Playwright as unavailable rather than manufacturing a passing shell URL.

## Document limits and security

PDF.js is loaded only on first PDF open through `loadPdfJs`. The integrator should inject a pinned local PDF.js ESM build and worker path. The controller caps input at 20 MiB, 80 pages, scale 0.5 to 3, and device-pixel ratio 2. It cancels outstanding render tasks and destroys the PDF document when replaced or closed.

Arbitrary HTML is never framed. It is classified `external-only`. Unsupported, encrypted, malformed, oversized, missing, or blocked documents produce one concise error with `open-original`. No proxy or analytics endpoint receives document bytes.

## Accessibility and resilience

The virtualization contract reports the complete result count independently of rendered rows. Focused rows are scrolled into the retained window. The document controller provides Escape close, focus trapping, scroll lock without scrollbar jump, and focus restoration.

The integration Playwright spec covers DOM bounds, rapid-query publication, document focus behavior, and offline reload. The final integrator must add axe-core scans against the issue #5 shell, filters, feed, expanded row, and dialog because those DOM elements do not exist in this isolated workstream.
