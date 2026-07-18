# DropFinder type-aware marketplace UI specification

## Supported product views

The marketplace exposes exactly one active primary product type at a time. The production selector contains four choices:

- Flower, `cannabis_flower`
- Vapes, `cannabis_vape`
- Mushrooms, `psilocybin_mushroom`
- Mushroom vapes, `psilocybin_vape`

There is no combined “All products” result mode. Cannabis edibles are not hidden behind a feature flag or accepted without a view. Edible-only and mixed edible offers remain unsupported until a future versioned product contract is implemented and accepted.

The active type is keyboard navigable, touch friendly, and reflected in the URL query string. A type change atomically:

1. closes product details and document viewers;
2. cancels obsolete detail and query work;
3. clears incompatible retained pages and ranges;
4. restores only state valid for the new type;
5. loads the selected compact index;
6. moves focus to the result summary;
7. updates the URL without a full reload.

## Shared interface

The page contains:

- app header and source-health control;
- visible single-choice product-type selector;
- search restricted to the active type;
- common and type-specific filters;
- explicit sort control;
- compact virtualized results;
- lazy expanded product details;
- document viewer;
- favorites and recoverable URL state.

Search may match normalized title, source title, vendor, supported type tags, strain, species, and type-specific identifiers exposed in the compact index. Unsupported records do not appear under a different supported type.

Common filters include vendor, stock, minimum completeness, favorites, and price. Filters with no values are disabled with an explanation rather than silently removed.

## Type-specific controls

### Flower

Filters may include lineage, weight, THC or THCA, terpene availability, and dominant terpene. The comparison sort is price per gram.

Compact rows show product, vendor, lineage, potency, weight, terpene summary, price, price per gram, stock, and completeness. Expanded details may show variants, potency evidence, effects, environment, terpene breakdown, provenance, and documents.

### Cannabis vape

Filters may include device type, volume, terpene availability, dominant terpene, and COA availability. The comparison sort is price per milliliter.

Compact rows show product, vendor, device type, volume, terpene summary, price, price per milliliter, stock, and completeness. Puff count and documents are expanded-only. The UI does not infer volume from grams.

### Psilocybin mushroom

Filters may include species, strain, weight, potency availability, and COA availability. The comparison sort is price per gram.

Compact rows show product, vendor, species, strain, weight, claimed or tested potency with explicit labels, price, price per gram, and completeness. Source claims and laboratory measurements remain separate.

### Psilocybin vape

Filters may include device type, volume, psilocybin-percentage availability, and COA availability. The comparison sort is price per milliliter.

Compact rows show product, vendor, device type, volume, labeled or tested percentage with explicit provenance, price, price per milliliter, and completeness. Source claims and laboratory measurements remain separate.

Outbound purchase actions are not exposed for controlled psilocybin products.

## Result lifecycle

Every first-page query owns a distinct revision. Query identity includes product type, generation, search, every filter, and sort. Load-more work from an older revision cannot append to a newer result set.

The UI must:

- keep one worker query in flight and at most one latest queued request;
- reject superseded requests promptly;
- retain a bounded number of virtual pages;
- evict data from React state as well as rendered DOM;
- preserve the visible anchor when pages are evicted;
- clear incompatible rows on generation or product-type change;
- keep an expanded row only while its product belongs to the active revision.

Loading, empty, blocked, stale, and failed states remain distinct. A blocked vendor is not rendered as a successful empty vendor.

## Expanded details and documents

Expanded data is lazy and generation-owned. A detail result is checked after fetch, body read, integrity verification, parse, cache insertion, and React state transition. Data from an older generation cannot enrich the current row.

The document overlay:

- moves focus into the dialog on open;
- contains forward and backward keyboard navigation;
- closes on Escape;
- restores the connected invoking element;
- prevents superseded sessions from restoring stale focus;
- retains the original public link when preview fails;
- validates image decode before readiness;
- applies one PDF startup deadline across runtime loading and document creation;
- releases tasks, object URLs, workers, and session resources on failure or close.

## Missing data and completeness

Missing optional data renders as `—` with an accessible field-specific label. Completeness is textual, such as `82% complete`, and never relies on color alone.

Completeness is informational. It does not imply quality, safety, authenticity, potency, legality, or vendor trustworthiness.

## Responsive behavior

Desktop uses a compact virtualized list or table. Mobile uses labeled cards with 44 px minimum touch targets and no document-level horizontal overflow at 320 CSS pixels. Type selection remains visible, expansion preserves scroll position, and the document viewer respects the safe-area viewport.

## Accessibility

Required behavior includes:

- a correct single-select tab or radio pattern for product type;
- persistent labels for compact mobile values;
- accessible missing-value announcements;
- textual completeness and stock state;
- `aria-expanded` and `aria-controls` for detail toggles;
- dialog focus containment and restoration;
- reduced-motion behavior;
- serious-violation accessibility checks for every supported type.

## Data loading and performance

The client loads only the selected compact index and shared vendor metadata. Detail data remains lazy:

1. load the active manifest entry;
2. verify the compact index hash;
3. initialize the matching query engine generation;
4. render and virtualize rows;
5. fetch one detail shard on expansion;
6. reject mixed-generation detail data;
7. cache by deployment, generation, and shard;
8. abort obsolete work on type or generation change.

COA documents are not prefetched for all results. Compact terpene summaries are precomputed during publication. Query parsing and filtering remain off the main thread when the worker is available.

## Saved state

Favorites use stable generalized product identity. Stored state may include active supported type, search per type, filters per type, sort per type, favorite product IDs, and favorite vendor IDs. State using an unsupported or retired type is safely invalidated rather than mapped to another category.

## Browser acceptance

Each supported product type must pass desktop Chromium, Firefox, and WebKit plus representative Android Chromium and iPhone WebKit projects.

Acceptance covers type-specific labels and metrics, missing data, completeness, bounded virtualization, no mixed generations, keyboard navigation, document lifecycle, minimum touch targets, responsive overflow, back and forward restoration, and accessibility checks.

The browser must not infer product type, scrape source documents, calculate missing business fields from titles, or maintain a second classifier separate from the publication pipeline.
