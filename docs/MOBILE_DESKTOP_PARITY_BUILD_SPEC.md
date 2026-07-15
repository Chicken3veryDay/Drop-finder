# DropFinder mobile desktop-parity build specification

## Status

Implementation specification for the responsive marketplace port.

- Product: DropFinder marketplace
- Target branch: `ui/mobile-desktop-parity`
- Source of truth: the existing desktop marketplace
- Delivery model: one responsive application, not separate desktop and mobile products

## 1. Objective

Deliver a complete mobile presentation of the existing desktop marketplace without changing its information architecture, shopper logic, terminology, data contracts, or visual language.

The mobile experience must feel like the desktop interface has been carefully reflowed for a smaller viewport. It must not introduce a second navigation model, alternate cards, reduced product information, mobile-only query behavior, or a separate state tree.

## 2. Product invariants

The following behavior must be identical at every viewport size:

1. Search matches the same fields.
2. Filters appear in the same order and use the same values.
3. Sort options and default sort are unchanged.
4. Result IDs and result ordering are identical for the same query state.
5. Active variant selection uses the same algorithm.
6. Price, original price, discount, weight, price per gram, product URL, image, COA, and terpene actions derive from the same active variant.
7. Only one product is expanded at a time.
8. Expansion closes when filtering removes that product.
9. Detail shards remain lazy-loaded.
10. Virtualization and paged loading remain active.
11. The document viewer uses the same platform capability and fallback behavior.
12. Keyboard, focus, reduced-motion, forced-color, and accessibility behavior remain intact.

## 3. Non-goals

This project must not:

- add bottom-tab navigation;
- add mobile-only routes;
- replace the desktop row with a different product-card component;
- change marketplace terminology;
- remove or abbreviate product fields;
- fork filters, sorting, or active-variant logic;
- introduce a second CSS theme;
- introduce a general UI framework;
- change catalog normalization or repair source data in the presentation layer;
- alter desktop layouts except where required to eliminate shared overflow or accessibility defects.

Pricing, stock, weight, and unknown-value correction remain data-pipeline responsibilities. The responsive UI must display the contract it receives without inventing values.

## 4. Supported viewport classes

### Wide desktop: 1181 px and above

Preserve the existing eight-column aligned marketplace table and four-column expanded detail layout.

### Compact desktop and landscape tablet: 901 to 1180 px

Preserve the aligned desktop row with compressed column tracks and the existing compact expanded layout.

### Tablet and phone: 320 to 900 px

Reflow the same eight row fields into a labeled responsive surface. Every field remains present and retains the desktop label, value, formatting, and interaction.

### Narrow phone: 320 to 479 px

Use a single readable content column where a two-column control or detail arrangement would cause truncation or horizontal overflow.

## 5. Shell requirements

### Header

- Preserve `dropfinder` and `Marketplace` exactly.
- Retain the same hierarchy, typography, colors, and border treatment.
- Respect `env(safe-area-inset-left)`, `env(safe-area-inset-right)`, and top safe area.
- Do not add mobile navigation controls.

### Marketplace container

- Preserve the current maximum width and centered desktop presentation.
- Use safe-area-aware inline padding on mobile.
- Prevent document-level horizontal scrolling.
- Keep all content above the browser gesture area through bottom safe-area padding.

## 6. Search requirements

- Preserve the same search input, placeholder, accessible name, and state.
- Preserve `/` focus behavior and Escape clear-then-blur behavior.
- Maintain a minimum 44 CSS-pixel touch height on coarse pointers.
- Prevent browser zoom caused by undersized form text on iOS.
- Search must not become a separate screen or overlay.

## 7. Filter requirements

The filter order remains:

1. Vendor
2. Lineage
3. Total THC
4. Weight
5. Price
6. Price/g
7. Sort

### Desktop

Keep the existing compact horizontal control row.

### Tablet and mobile

- Reflow the same controls into the available width.
- Use two columns where controls remain legible.
- Use one column on narrow phones.
- Preserve native `details`, checkbox, number input, and select semantics.
- Open multiselect content inline on small screens so it cannot escape the viewport.
- Keep multiselect options scrollable with a bounded height.
- Preserve immediate filtering. Do not add Apply or staged-filter state.
- Preserve the same numeric values and range semantics.

## 8. Result summary requirements

- Preserve the same result count and refreshing state.
- Keep the result announcement live region behavior.
- Do not hide the result count behind a mobile toolbar.

## 9. Marketplace row requirements

### Shared semantic structure

The existing `MarketplaceRow` and its eight `.df-cell` elements remain the only row implementation.

Field order remains:

1. Vendor
2. Strain Name
3. Lineage
4. Total THC
5. Weight
6. Price
7. Price/g
8. Rating

### Desktop

Preserve the existing aligned grid and column header.

### Tablet and mobile

- Hide only the separate desktop column-header row.
- Display the same `.df-cell` elements in a responsive labeled grid.
- Use each existing `data-label` value as the visible mobile field label.
- Preserve lineage tinting, hover/focus/expanded states, numeric formatting, discount presentation, and vendor identity.
- Do not truncate primary product identity where wrapping is possible.
- Keep secondary values compact without removing them.
- Preserve Enter and Space row activation.
- Ensure the row remains one focusable control with the same `aria-expanded` and `aria-controls` relationship.

## 10. Expanded-detail requirements

The same inline `ExpandedDetail` component must be used at every viewport.

Mobile reflow requirements:

- Preserve image, weight selector, price, price per gram, effects, grow environment, product link, COA action, and terpene action.
- Reflow the four desktop detail regions into one or two columns based on available width.
- Keep the product image bounded and proportional.
- Give the weight selector and all actions at least 44 CSS pixels of touch height.
- Do not convert details into a separate route or product page.
- Preserve document invoking-element focus restoration.

## 11. Document-viewer requirements

- Preserve the same viewer capability and fallback component.
- Desktop remains centered with bounded dimensions.
- Mobile occupies the available dynamic viewport.
- Respect all safe-area insets.
- Keep title, Open original, and Close controls available.
- Allow the header actions to wrap without overlap.
- Keep document content independently scrollable.
- Preserve Escape close and focus trapping.

## 12. Accessibility requirements

- No automated axe violations in integrated marketplace flows.
- All interactive targets are at least 44 by 44 CSS pixels on coarse pointers where layout permits.
- Visible focus remains present for keyboard users.
- Mobile labels are generated from existing semantic `data-label` attributes rather than duplicated hard-coded wording.
- Color is never the only carrier of lineage or state information.
- Text remains readable at 200% browser zoom.
- Content remains operable with reduced motion and forced colors.
- No hover-only action may become unreachable on touch devices.

## 13. Overflow and viewport requirements

At 320, 360, 375, 390, 412, 430, 768, and 900 CSS pixels:

- `document.documentElement.scrollWidth <= window.innerWidth`;
- no filter menu extends outside the viewport;
- no row value is accessible only through page-level horizontal scrolling;
- expanded details remain fully reachable;
- the document viewer does not exceed the dynamic viewport;
- safe-area padding does not create extra overflow.

Intentional internal scrolling is permitted only for:

- multiselect option lists;
- document content;
- the virtualized marketplace viewport managed by the platform capability.

## 14. Performance requirements

Responsive changes must not alter the existing data or rendering architecture.

- Continue to render a bounded number of product rows.
- Do not duplicate desktop and mobile DOM trees.
- Do not use JavaScript viewport listeners for layout that CSS can perform.
- Do not remount the marketplace when crossing a breakpoint.
- Do not trigger a catalog-wide rerender solely for responsive presentation.
- Keep detail loading lazy.
- Keep query execution in the configured worker capability.
- Keep reduced-motion behavior free of unnecessary animations.

## 15. Test plan

### Integrated parity test

Run on desktop Chromium, Firefox, WebKit, mobile Chromium, and mobile WebKit:

- marketplace loads a nonzero catalog;
- search is visible and keyboard focus behavior works;
- virtualized DOM remains bounded;
- a row expands and exposes Product link;
- axe reports no violations.

### Mobile-specific parity test

Run only when viewport width is 900 px or lower:

- the page has no horizontal document overflow;
- all seven filter/sort groups remain visible;
- row cells preserve the exact eight desktop labels;
- every row field is visible;
- multiselect content opens within the document flow;
- a row expands without navigation;
- weight selection and product action remain accessible;
- primary touch controls meet the minimum target size;
- the page remains overflow-free after expansion.

### Browser matrix

- Desktop Chrome
- Desktop Firefox
- Desktop Safari/WebKit
- Pixel 7 Chromium
- iPhone 13 WebKit

## 16. Files and ownership

### New

- `web/src/features/marketplace/marketplace-mobile-parity.css`
- `docs/MOBILE_DESKTOP_PARITY_BUILD_SPEC.md`

### Updated

- `web/src/app/main.tsx`
- `web/src/features/marketplace/README.md`
- `web/tests/e2e/integrated-app.spec.mjs`
- `web/playwright.config.mjs`

The implementation intentionally avoids modifying marketplace query logic, catalog contracts, active-variant selection, virtualization, and document capability code.

## 17. Acceptance criteria

The mobile port is complete when all statements below are true:

- [ ] Mobile and desktop use the same component tree and marketplace state.
- [ ] All desktop fields and actions are present on mobile.
- [ ] Filter order, values, and immediate behavior are unchanged.
- [ ] Sort behavior and default sort are unchanged.
- [ ] Result identity and ordering are viewport-independent.
- [ ] Mobile rows visibly identify all eight desktop fields.
- [ ] Expanded details remain inline and complete.
- [ ] No page-level horizontal overflow exists at supported widths.
- [ ] Controls are touch-operable and keyboard-operable.
- [ ] Safe areas and dynamic viewport height are respected.
- [ ] Desktop presentation remains unchanged above the responsive breakpoint.
- [ ] Mobile Chromium and mobile WebKit projects pass.
- [ ] Integrated axe checks pass.
- [ ] Virtualized DOM remains bounded.
- [ ] No alternate mobile product architecture was introduced.

## 18. Rollback

The responsive port is isolated to one additive stylesheet, one stylesheet import, documentation, and tests. Rollback consists of removing the mobile parity import and stylesheet, then reverting the accompanying documentation and browser-matrix changes. No catalog or persistence migration is required.
