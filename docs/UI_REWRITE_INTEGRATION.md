# DropFinder five-branch UI rewrite integration runbook

An isolated workstream is not the completed rewrite. GitHub, regrettably, does not merge architectural intent by telepathy.

## 1. Verify exact inputs

Record the head SHA, draft PR, issue evidence, and CI result for issues #5 through #9. Re-read remote `main`; autonomous catalog commits can move it. Reject stale screenshots, neighboring workflow runs, and issue checkboxes as proof of an exact head.

## 2. Integration order

Create a dedicated integration branch from current `main`, then combine:

1. issue #5 foundation and capability registry;
2. issue #7 vendor evidence and document adapters;
3. issue #6 catalog schema v4 and generated publication;
4. issue #9 performance/platform capability;
5. issue #8 marketplace feature;
6. conflict repair and the complete validation stack.

Do not merge sibling workstreams into one another before this integration branch.

## 3. Collision-prone files

Inspect rather than auto-accept conflicts in:

- `cloud_pages/sw.js`, `app-shell.json`, `manifest.webmanifest`, `index.html`, and generated assets;
- frontend `package.json`, lockfile, Vite and Playwright configuration;
- GitHub Actions workflows;
- generated manifest/index/vendor/detail/document data.

Preserve issue #6 generation metadata, issue #9 complete-generation caching, issue #5 shell metadata, issue #7 document identity, and issue #8 marketplace behavior. Do not retain the old service worker merely because fewer lines are emotionally soothing.

## 4. Interface compatibility

Verify issue #5 accepts `registerCapability(name, { contractVersion, instance })`, or add one narrow adapter. Issue #8 should consume only:

- `CatalogGenerationClient.initialize`, `refresh`, `loadDetail`, `subscribe`, `snapshot`;
- `MarketplaceQueryEngine.initialize`, `query`, `dispose`;
- `VirtualMarketplaceAdapter.replace`, `appendPage`, `requestPage`, `setViewport`, `measure`, `window`, `focus`;
- `DocumentViewerCapability.open`, `close`, navigation/zoom methods, `renderPage`, `handleKeyDown`, `subscribe`;
- `PwaGenerationCoordinator.register`, `activateReadyGeneration`, `cacheOpenedDocument`, `subscribe`.

Pass `result.queryKey` to virtual `replace`/`appendPage` for endless pages. Confirm issue #7 supplies selected product, variant, and document identity without issue #9 guessing mappings. Confirm issue #6 emits schema 4, immutable generation IDs, byte counts, hashes, and matching envelopes.

## 5. Clean install and deterministic validation

From a clean checkout of the exact integration SHA:

```bash
python -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run benchmark
npm --prefix web run build
npm --prefix web run analyze:chunks
```

Verify the initial marketplace chunk excludes PDF.js and its worker, while first PDF open loads the emitted dynamic chunks.

## 6. Python and generated-data validation

Run the full Python suite plus focused catalog/vendor tests. Regenerate deterministic fixtures. Verify manifest, index, detail, vendor, and document metadata agree on schema and generation. Exercise missing, malformed, duplicate, oversized, interrupted, and rollback paths. Validate that a partial publication never replaces the last complete generation.

## 7. Browser, accessibility, and performance validation

```bash
npm --prefix web run test:e2e:install
npm --prefix web run test:e2e
```

Run Chromium, Firefox, WebKit, and mobile. Retain traces/screenshots/reports on failure. Keep axe-core scans for the shell, filters, feed, expanded row, and dialog plus explicit keyboard tests for filter traversal, virtualized-row focus, dialog trapping, Escape close, and focus restoration.

Capture browser/OS/hardware, fixture size, p50/p95 query latency, long tasks, rendered row and DOM-node maxima, expansion/weight latency, detail-cache retention, PDF first-open/page-change timing, and offline/update behavior. Do not relax budgets to make a red build less socially awkward.

## 8. Static publication smoke

Serve the exact production output under a nested path. Verify shell, worker, data, document, manifest, icon, and service-worker URLs on GitHub Pages and raw.githack. Confirm no private headers, cookies, logs, worker evidence, raw document text, or unpublished source data enter the artifact.

## 9. Autonomous workflow on the exact commit

Trigger the autonomous catalog workflow from the integrated commit. Verify every retrieval shard, merge/admission step, UI build, publication, and post-publication check. Fetch `gh-pages` and compare generation ID and required blob hashes to the source artifact. A successful run from another commit proves another commit.

## 10. Rollback

Record pre-integration `main` and `gh-pages` SHAs. On publication failure, stop promotion, restore the prior known-good `gh-pages` tree, and retain the previous complete data cache. Do not delete it until the replacement has loaded both online and offline.

## 11. Completion rule

Declare the rewrite complete only after the integrated SHA passes clean install, Python tests, frontend unit/build/chunk checks, browser/a11y/performance suites, nested-path static smoke, autonomous publication, exact-artifact verification, and rollback rehearsal. Issue #9 alone supplies platform capability, not a deployed marketplace.
