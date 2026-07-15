# Vendor COA and terpene-document coverage

Generated from `data/vendor_profiles.json` after a public first-party evidence pass on 2026-07-15 UTC.

| Vendor ID | Vendor | COA | Terpenes | Discovery strategy | First-party index or fallback |
|---|---|---|---|---|---|
| `arete` | Arete | `public` | `partial` | `central_index_plus_product_links` | https://arete.shop/lab-reports |
| `black_tie_cbd` | Black Tie CBD | `public` | `public` | `central_index_plus_product_links` | https://www.blacktiecbd.net/pages/lab-results-and-coas |
| `crysp` | Crysp | `partial` | `uncertain` | `product_page_links` | Product-page discovery only / no index observed |
| `five_leaf_wellness` | Five Leaf Wellness | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `green_unicorn_farms` | Green Unicorn Farms | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `hello_mary` | Hello Mary | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `holy_city_farms` | Holy City Farms | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `loud_house_hemp` | Loud House Hemp | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `lucky_elk` | Lucky Elk | `public` | `partial` | `central_index_gallery` | https://luckyelk.com/pages/coa-tests |
| `preston_herb_co` | Preston Herb Co. | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `pure_roots_botanicals` | Pure Roots Botanicals | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `quantum_exotics` | Quantum Exotics | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `secret_nature` | Secret Nature | `public` | `public` | `central_index_named_documents` | https://secretnature.com/pages/laboratory-test-results |
| `sherlocks_glass` | Sherlocks Glass & Dispensary | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `smoky_mountain_cbd` | Smoky Mountain CBD | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `stoney_branch_farms` | Stoney Branch Farms | `not_observed` | `not_observed` | `product_page_links` | Product-page discovery only / no index observed |
| `wnc_cbd` | WNC CBD | `public` | `partial` | `central_index_plus_product_links` | https://wnc-cbd.com/lab-reports-legal-documentation-20/ |

## Meaning of availability

- `public`: a first-party public index or direct product-linked document path was observed.
- `partial`: public lab evidence exists, but product/batch completeness is not universal or could not be proved.
- `not_observed`: the inspected public route did not expose a lab document or index. This is not proof of absence.
- `inaccessible`: the expected resource could not be inspected safely.
- `unsupported`: the source is known but cannot be parsed safely by the current bounded implementation.
- `uncertain`: evidence is insufficient or contradictory.

## Adapter contract

The parser preserves document provenance, stable IDs, parse status, limitations, and explicit mapping scope. Missing or unsupported lab data never removes an otherwise accepted catalog product. OCR is deliberately unsupported; scanned reports remain visible as unsupported evidence instead of being guessed. Redirects are limited to the vendor and declared CDN hosts, responses are size/time bounded, and private or local network targets are rejected.
