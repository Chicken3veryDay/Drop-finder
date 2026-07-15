# DropFinder five-branch UI rewrite integration runbook

An isolated workstream is not the completed rewrite. GitHub, regrettably, does not merge architectural intent by telepathy.

## 1. Verify inputs

Record the exact head SHA, draft PR, issue evidence, and CI status for issues #5 through #9. Confirm every branch is based on a known `main` commit and contains only its declared ownership area. Do not use a stale PR title or issue checkbox as evidence of a tested head.

## 2. Integration order

Create a dedicated integration branch from the latest remote `main`, then combine:

1. Issue #5 foundation and capability registry.
2. Issue #7 vendor evidence and document adapters.
3. Issue #6 catalog schema v4 and generated publication.
4. Issue #9 performance/platform capability.
5. Issue #8 marketplace feature.
6. Repair integration conflicts and run the complete validation stack.

Do not merge sibling branches into each other.

## 3. Collision-prone files

Inspect rather than accepting an automatic conflict resolution for:

- `cloud_pages/sw.js`
- `cloud_pages/manifest.webmanifest`
- `cloud_pages/index.html` and generated frontend assets
- frontend `package.json` and lockfile
- Playwright/Vite/build configuration
- GitHub Actions workflow YAML
- generated manifest/index/vendor/detail data

Preserve issue #6 generation metadata, issue #9 complete-generation caching, issue #5 shell metadata, and issue #8 marketplace behavior. Never retain the old service worker merely because it has fewer lines and therefore looks emotionally manageable.

## 4. Interface checks

Verify the issue #5 registry accepts `registerCapability(name, { contractVersion, instance })`, or add a narrow adapter. Confirm issue #8 consumes only:

- `CatalogGenerationClient.initialize`, `refresh`, `loadDetail`, `subscribe`, and `snapshot`
- `MarketplaceQueryEngine.initialize`, `query`, and `dispose`
- `VirtualMarketplaceAdapter.replace`, `appendPage`, `requestPage`, `setViewport`, `measure`, `window`, and `focus`
- `DocumentViewerCapability.open`, `close`, navigation/zoom methods, `renderPage`, `handleKeyDown`, and `subscribe`
- `PwaGenerationCoordinator.register`, `activateReadyGeneration`, `cacheOpenedDocument`, and `subscribe`

Confirm issue #7 passes selected product, variant, and document identity without issue #9 guessing document mappings. Confirm issue #6 emits schema version 4, immutable generation IDs, byte counts, content hashes, and matching JSON envelopes.

## 5. Clean install and frontend validation

From a clean checkout of the exact integration SHA:

```bash
python -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run benchmark
npm --prefix web run build
```

Run chunk analysis and verify PDF.js and its worker are absent from the initial marketplace chunk and loaded only after opening a PDF.

## 6. Python and generated-data validation

Run the repository's full Python test command plus focused catalog/vendor suites. Regenerate deterministic fixtures. Verify manifest/index/detail/vendor/document metadata agree on schema and generation. Check missing/malformed/oversized assets, duplicate identities, interrupted generation publication, and rollback to the previous complete generation.

## 7. Browser, accessibility, and performance validation

Set `DROPFINDER_E2E_URL` to the integrated static preview and run:

```bash
npx playwright install --with-deps chromium firefox webkit
npx playwright test --config web/playwright.config.mjs
```

Run Chromium, Firefox, WebKit, and mobile viewport projects. Add axe-core scans for the shell, filters, result feed, expanded row, and document dialog. Keep explicit keyboard tests for filter traversal, virtualized-row focus, dialog trapping, Escape close, and focus restoration.

Capture hardware, browser versions, fixture size, p50/p95 query latency, long tasks, rendered row and DOM-node maxima, expansion/weight-change latency, detail-cache retention, PDF first-open/page-change timing, and offline/update results. Do not loosen budgets to make a red build aesthetically pleasing.

## 8. Static publication verification

Build with the repository base path and serve the exact output under a nested path. Verify all shell, worker, data, document, manifest, icon, and service-worker URLs remain relative-path safe on GitHub Pages and raw.githack. Confirm no private headers, cookies, logs, worker evidence, raw document text, or unpublished data enter the artifact.

## 9. Live autonomous workflow verification

Trigger the autonomous catalog workflow on the exact integrated commit. Verify all worker shards, catalog generation, UI build, publication, and post-publication validation. Re-read `gh-pages` and compare generation ID plus required blob hashes to the source artifact. A workflow run from a neighboring commit is not evidence for the integrated head.

## 10. Rollback

Record the pre-integration `main` and `gh-pages` SHAs. If publication validation fails, stop promotion, restore the prior known-good `gh-pages` tree, and leave the prior complete data cache addressable. Do not delete the last-known-good generation until the replacement has loaded online and offline.

## 11. Completion rule

Declare the rewrite complete only after the integrated commit passes clean install, Python tests, frontend tests, browser/a11y/performance suites, nested-path static smoke, autonomous workflow, exact-artifact verification, and rollback rehearsal. Issue #9 by itself supplies platform capability, not a deployed marketplace.
