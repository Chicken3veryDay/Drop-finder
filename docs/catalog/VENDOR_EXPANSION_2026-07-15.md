# Vendor expansion and age-control audit

Date: 2026-07-15

## Scope and safety boundary

This expansion registers 22 additional first-party online storefronts for strict live validation. Registration is not publication. Every route remains behind DropFinder's existing product-level requirements for explicit THCA and flower evidence, supported loose-flower form, product URL, price, and stock. A failed, blocked, empty, mixed-form, or weakly evidenced source is quarantined.

Research was limited to public storefront, category, product, lab, and unauthenticated catalog representations. No purchase, checkout completion, account creation, identity upload, or age-control bypass was attempted.

Age-control labels mean:

- **Verification**: first-party evidence of an identity or document verification system.
- **Confirmation**: a self-attested Yes/No, Enter, or "I am 21+" control.
- **Unknown**: the retrieved public representation did not establish either mechanism.
- **No gate observed**: an observation only, never proof that no later control exists.

A legal disclaimer or "21+ only" sentence is not promoted to Confirmation unless an interactive self-attestation control was observed. No new vendor was labeled Verification without direct provider evidence.

## Added storefronts

| Vendor | Primary custom route | Route strategy | Age result | Research confidence | Important limitation |
|---|---|---|---|---|---|
| Cali Canna | `https://calicanna.cc/` | Shopify candidates plus HTML | Unknown | High | 21+ language observed, control/provider not established |
| Flow Gardens | `/collections/flower-type-1-flower-high-thca` | Shopify JSON plus HTML | Confirmation | High | None material |
| Dr. Ganja | `/thca-flower` | Woo Store API plus HTML | Confirmation | High | API availability is rechecked by live CI |
| Hemp Hop | `/collections/thca-flower-and-prerolls` | Shopify JSON plus HTML | Unknown | High | Mixed collection; pre-rolls remain excluded |
| Beleafer | `/product-category/thca-flower/` | Woo Store API plus HTML | Unknown | Medium | Current handle/API require live validation |
| Wildflower Hemp Co | `/collections/flower` | Shopify JSON plus HTML | Unknown | High | Mixed collection requires explicit THCA evidence |
| Gold Canna | `/collections/all` | Shopify JSON plus HTML | Confirmation | High | Storewide route requires strict form filtering |
| Botany Farms | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Route was not fully retrievable during research |
| Bay Smokes | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Must pass live CI before publication |
| The Hemp Collect | `/collections/thca-flower` | Shopify JSON plus HTML | Confirmation | High | None material |
| Snapdragon Hemp | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Route and gate require live confirmation |
| CBD Hemp Direct | Woo search plus storefront HTML | Woo Store API plus HTML | Unknown | Medium | Request-verification layer may block workers |
| Eight Horses Hemp | `/collections/hemp-flower-type-1-2` | Shopify JSON plus HTML | Confirmation | High | Mixed Type 1/2 collection requires THCA evidence |
| Veteran Grown Hemp | `/product-category/thca-flower/` | Woo Store API plus HTML | Unknown | Medium | Route must pass live CI |
| CannaNC | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Platform/handle require live confirmation |
| LIT Farms | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Collection handle requires live confirmation |
| Simply Mary | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Route must pass live CI |
| Earthy Select | Shopify, Woo, and HTML candidates | Multi-platform fallbacks | Unknown | Medium | Platform/handle require live confirmation |
| Exhale Wellness | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Route must pass live CI |
| Plain Jane | collection plus storefront HTML | Shopify candidate plus HTML | Unknown | Medium | THCA collection handle requires live confirmation |
| Great CBD Shop | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Multi-brand catalog needs strict dedupe |
| Mood | `/collections/thca-flower` | Shopify candidate plus HTML | Unknown | Medium | Rendering and route require live confirmation |

The machine-readable source of truth is `data/vendor_expansion.json`. Each vendor has its own ordered routes, HTML fallbacks, recognized product paths, age classification, evidence URL, observation timestamp, and limitations.

## Existing vendor metadata

Catalog v4 previously built without passing `data/vendor_profiles.json`, so active vendors could be emitted as `minimal_generated_from_catalog` with an `uncertain` age result even when audited metadata already existed. Catalog generation now merges:

1. `data/vendor_profiles.json` for the 17 existing audited vendors.
2. `data/vendor_expansion.json` for the 22 new vendors.

Nested age metadata is normalized into the catalog's flat vendor contract, including classification, provider, scope, summary, and evidence reference. The build also publishes `catalog-v4/vendor-age-verification.json` for the browser.

## Expanded-row UI

The marketplace loads the public age index and adds one compact fact to an expanded product row:

- `Age check: Verification`
- `Age check: Confirmation`
- `Age check: No gate observed`
- `Age check: Unknown`

The badge title and accessible label retain the provider, scope, and research summary when available. Missing or older metadata never blocks product browsing.

## Deliberate exclusions

The following were not admitted during this pass:

- **Top Cola**: password-protected storefront representation, no maintainable public product route.
- **Piur Select**: redirected into another storefront/collection and would duplicate an existing source identity.
- **Rogue Origin**: retrieved catalog emphasis did not establish qualifying high-THCA loose flower for this expansion.
- **JK Distro / Just Kali Direct**: rebrand/redirect state made the source identity and canonical catalog ambiguous.

## Validation contract

`python scripts/autonomous_worker_v4.py --self-test` validates registry size, uniqueness, route types, source installation, fallbacks, and retained strict worker behavior. Catalog tests validate current-plus-expansion profile merging and ensure self-attestation is never surfaced as identity verification. Frontend tests validate name normalization, classification mapping, idempotent expanded-row injection, and accessible labels.
