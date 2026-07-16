# DropFinder type-aware marketplace UI specification

## Purpose

This specification defines the shopper-facing migration before any new product category is added to production. It preserves the current compact marketplace character while preventing a generic one-size-fits-none table from flattening categories with different quantities, evidence, and comparison metrics.

## Core interaction model

The marketplace has exactly one active primary product type.

The active type is controlled by a segmented selector near the top of the page:

- Flower
- Vapes
- Edibles
- Mushrooms
- Mushroom vapes

The selector is single-choice, keyboard navigable, touch friendly, and reflected in the URL query string:

```text
?type=cannabis_flower
?type=cannabis_vape
?type=cannabis_edible
?type=psilocybin_mushroom
?type=psilocybin_vape
```

Changing type performs an atomic view transition:

1. close open product details and document viewers;
2. cancel obsolete detail-shard requests;
3. retain only filters meaningful to both the old and new type;
4. reset type-specific ranges and sort order;
5. load the selected type's compact index;
6. move focus to the result summary without jumping the page unexpectedly;
7. update the URL without a full reload.

There is no combined “All products” result mode.

## Information architecture

### Page header

- DropFinder wordmark
- current section label
- source-health control
- favorites control

### Product-type selector

The selector sits below the app header and above search. It remains visible when filters wrap on mobile. It is not hidden inside a menu because changing product type changes the meaning of every row, filter, metric, and sort.

### Search

Search operates only within the active primary type. It matches normalized title, source title, vendor, type tags, strain, species, and type-specific identifiers exposed in the compact index.

Search does not pull secondary-tagged records from another primary-type index. A mixed THCA + mushroom gummy with `primary_type=cannabis_edible` remains in Edibles and does not appear in Mushrooms.

### Filters

Common filters:

- vendor
- stock
- minimum completeness score
- favorites only
- price range

Type-specific filters:

#### Flower

- lineage
- weight range
- total THC / THCA range
- terpene availability
- dominant terpene

#### Cannabis vape

- device type
- volume range
- terpene availability
- dominant terpene
- COA available

#### Cannabis edible

- piece-count range
- total labeled active amount range
- amount-per-piece range
- terpene availability
- dominant terpene
- COA available

#### Psilocybin mushroom

- species
- strain
- weight range
- potency available
- COA available

#### Psilocybin vape

- device type
- volume range
- psilocybin-percentage range
- COA available

Filters with no values in the loaded index are disabled rather than omitted, preserving layout stability and explaining why the filter cannot currently narrow results.

## Sorting

Every active type supports:

- relevance
- current price, low to high
- current price, high to low
- completeness, high to low
- newest collected

The comparison sort changes with the active type:

- flower: price per gram
- cannabis vape: price per milliliter
- cannabis edible: price per 100 mg
- psilocybin mushroom: price per gram
- psilocybin vape: price per milliliter

The UI labels the metric explicitly. It never displays a generic “unit price” label.

## Compact row design

### Shared visual grammar

Every compact row uses the same structural rhythm:

1. identity zone: product title, vendor, primary type, secondary tags;
2. category facts: type-specific fields;
3. evidence/value zone: terpene or potency summary, price, comparison metric, completeness;
4. stock state and expansion affordance.

Missing data renders as `—`. The em dash must have an accessible label when the column meaning is not obvious, for example `aria-label="Terpenes not published"`.

The completeness score appears as plain text such as `82% complete`, not a color-only badge. Color may reinforce the value but never replace it.

Secondary type tags are visually quieter than the primary type. They are not clickable category switches because they do not change the product's primary index.

### Flower row

Desktop columns:

- Product
- Vendor
- Lineage
- Total THC / THCA
- Weight
- Terpenes
- Price
- $/g
- Completeness

Mobile card order:

- product and tags
- vendor
- price and $/g
- weight and potency
- lineage
- terpenes
- completeness

Terpenes show up to three dominant normalized names plus total terpene percentage when available. Example:

```text
Myrcene · Limonene · Caryophyllene · 2.8% total
```

### Cannabis vape row

Desktop columns:

- Product
- Vendor
- Device type
- Volume
- Terpenes
- Price
- $/mL
- Completeness

Mobile card order:

- product and tags
- vendor
- price and $/mL
- device type and volume
- terpenes
- completeness

Puff count and COA are not compact fields.

### Cannabis edible row

Desktop columns:

- Product
- Vendor
- Pieces
- Total amount
- Per piece
- Terpenes
- Price
- $/100 mg
- Completeness

Mobile card order:

- product and tags
- vendor
- price and $/100 mg
- total amount and per-piece amount
- piece count
- terpenes
- completeness

The compact row does not contain format, cannabinoid summary, flavor, ingredients, allergens, or serving size.

### Psilocybin mushroom row

Desktop columns:

- Product
- Vendor
- Species
- Strain
- Weight
- Potency
- Price
- $/g
- Completeness

Mobile card order:

- product and tags
- vendor
- price and $/g
- species and strain
- weight and potency
- completeness

### Psilocybin vape row

Desktop columns:

- Product
- Vendor
- Device type
- Volume
- Psilocybin %
- Price
- $/mL
- Completeness

Mobile card order:

- product and tags
- vendor
- price and $/mL
- device type and volume
- psilocybin percentage
- completeness

## Expanded details

Expanded details are type-specific but share four zones:

1. image and identity;
2. variant selector and normalized price metric;
3. detailed facts and provenance;
4. documents and actions.

### Flower expanded details

- package variants
- potency details and method
- lineage
- effects
- grow environment
- terpene table
- COA documents
- field provenance

### Cannabis vape expanded details

- volume variants
- device type
- puff count
- full terpene table
- COA documents
- field provenance

Do not add device compatibility, cannabinoid summary, rechargeable, or blend-ingredient fields.

### Cannabis edible expanded details

- piece-count and amount variants
- total labeled active amount
- amount per piece
- full terpene table
- COA documents
- field provenance

Do not add format, cannabinoid summary, flavor, ingredients, allergens, or serving-size fields.

### Psilocybin mushroom expanded details

- species
- strain
- weight variants
- claimed potency
- tested potency when available
- COA documents
- field provenance

Source claims and laboratory values must have separate labels and must never be merged into one number.

### Psilocybin vape expanded details

- volume variants
- device type
- claimed psilocybin percentage
- tested percentage when available
- COA documents
- field provenance

Source claims and laboratory values must have separate labels and must never be merged into one number.

The normalized shopper view does not expose outbound purchase actions for controlled psilocybin products.

## Terpene presentation

Compact rows receive a concise terpene summary. Expanded details receive a sortable analyte table:

- normalized terpene name
- raw source label
- value
- unit
- source type
- batch or variant scope
- document date when public

Rules:

- Show `—` when no terpene information is published.
- Show `Published, not quantified` when names are published without amounts.
- Show total terpene percentage only when explicitly published or derived from compatible percentage units.
- Do not silently convert mg/g to percent without preserving the formula and original unit.
- Do not display a document-derived terpene as product-wide when the document is variant- or batch-specific.

## Completeness presentation

The compact score is a percentage. Expanded details include a disclosure titled `Data completeness` with:

- available common fields;
- available type-specific fields;
- evidence sources;
- missing fields;
- last collection time.

The score is informational. It does not imply product quality, safety, potency, authenticity, or vendor trustworthiness.

## Empty, loading, blocked, and stale states

### Loading

Skeleton rows match the active type's column geometry. Type changes must not briefly show rows from the previous index.

### No matching products

Display the active type and current filters. Offer `Clear filters`, not `Search all product types`.

### Source blocked

Blocked vendors remain visible in source health with:

- attempted route count;
- last HTTP result;
- last successful collection when one exists;
- whether saved fixture tests still pass.

Blocked state is not rendered as an empty successful vendor.

### Stale data

Rows older than the publication freshness threshold retain their data but display a stale indicator in expanded details. Staleness does not fabricate current stock or price.

## Responsive behavior

### Wide desktop

- single compact table/list surface;
- product-type selector remains one line when space permits;
- filters scroll horizontally only before the first responsive breakpoint;
- expanded details use a multi-column grid without covering neighboring rows.

### Tablet

- selector may wrap into two rows but remains fully visible;
- filters become a two-column control grid;
- low-priority column headers collapse into labeled row cells;
- expanded details use two columns.

### Mobile

- selector becomes a horizontally scrollable, snap-aligned segmented control with 44 px minimum touch targets;
- cards use labeled facts rather than compressed table columns;
- document viewer uses the full safe-area-aware viewport;
- the active type, search term, and filters remain recoverable after browser back/forward navigation;
- no document-level horizontal overflow at 320 px CSS width;
- expansion does not reset scroll position.

## Accessibility

- Product-type selector uses a single-select tab or radio pattern with correct keyboard behavior.
- Every compact value has a persistent textual label on mobile.
- Missing fields announce the field name and that the value is unavailable.
- Completeness is readable without color.
- Type tags and stock state meet contrast requirements.
- Expanded details use a button with `aria-expanded` and `aria-controls`.
- Document viewer traps focus only while open and restores focus on close.
- Reduced-motion mode removes type-transition and expansion animation.
- Browser tests run Axe checks in every active product type.

## Data loading and performance

The generalized catalog publishes one compact index per primary type. The client loads only the selected index and shared vendor metadata.

Detail data remains lazy:

1. load active type manifest entry;
2. hash-check compact index;
3. render and virtualize rows;
4. fetch one detail shard on expansion;
5. reject mixed-generation detail data;
6. cache by generation and shard;
7. abort obsolete requests on type change.

Performance budgets:

- no full detail catalog in the initial bundle;
- bounded DOM virtualization remains active;
- type change does not load another type until selected;
- COA documents are never prefetched for every result;
- terpene compact summaries are precomputed during publication;
- mobile interaction targets remain responsive while indexes are parsed in the query worker.

## Favorites and saved state

Favorites are keyed by stable generalized product identity and survive the flower migration when source identity remains unchanged.

Stored state includes:

- active product type;
- search term per type;
- filters per type;
- sort per type;
- favorite product IDs;
- favorite vendor IDs.

Changing type restores that type's last search/filter state rather than applying incompatible ranges from another type.

## Browser acceptance matrix

Every product type must pass:

- desktop Chromium
- desktop Firefox
- desktop WebKit
- Pixel-class mobile Chromium
- iPhone-class mobile WebKit

Required assertions:

- exactly one active product type;
- type-specific columns and labels;
- no excluded fields;
- terpene compact field on all cannabis types;
- puff count and vape COA expanded-only;
- em dash for missing optional values;
- visible completeness score;
- correct comparison metric;
- mixed tags without duplicate cross-view records;
- bounded virtualization;
- no horizontal document overflow;
- minimum touch-target sizing;
- no serious accessibility violations;
- safe browser back/forward restoration.

## Implementation constraint

The new UI must be built from the accepted generalized data contract. It must not infer product type, calculate missing business fields from titles, scrape documents in the browser, or maintain a second category classifier separate from the publication pipeline.