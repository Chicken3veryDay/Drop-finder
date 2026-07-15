# Arete vendor compliance and lab-source report

**Vendor ID:** `arete`
**Verified:** 2026-07-15T02:25:00Z
**Canonical origin:** https://arete.shop
**Configured catalog route:** https://arete.shop/l/national/products/category/thca-flower

## Research boundary

This report covers publicly reachable first-party pages and document links. It does not complete a purchase, enter checkout, create an account, upload identification, solve or bypass an access gate, or infer hidden behavior from marketing claims. A missing observation is recorded as uncertain or not observed rather than as proof of absence.

## Age-verification finding

- Classification: `uncertain`
- Provider: `none_observed`
- Scope: `uncertain`
- Finding: The public category page inspected did not expose a clear 21+ gate or an identity-verification requirement in the retrieved representation. No checkout was attempted.

Self-attestation is intentionally distinct from identity verification. This adapter does not click through, persist an age cookie, or interact with checkout.

## Laboratory-document finding

- COA availability: `public`
- Terpene availability: `partial`
- Finding: A first-party Labs navigation item resolves to a centralized lab-report page, and the flower category states products are independently tested. Product/batch matching must be derived from report labels and product context.

### First-party lab indexes

- https://arete.shop/lab-reports

## Discovery and parsing strategy

- Discovery strategy: `central_index_plus_product_links`
- Parser strategy: `safe_auto_structured_html_json_pdf_text`
- Product-page discovery: `true`
- Structured API discovery: `true`
- OCR: unsupported by design
- Redirect policy: `same_vendor_or_declared_cdn_hosts_only`

The adapter accepts only bounded public HTTP(S) resources on the declared host allowlist. It extracts structured JSON, structured HTML, plain text, and a deliberately limited uncompressed text-PDF subset. Scanned, encrypted, compressed-without-a-vetted-parser, or otherwise unsupported documents remain explicit unsupported records.

## Mapping contract

Documents are mapped only with explicit evidence. Ranking is deterministic: exact variant identifiers, exact batch identifiers, exact normalized weight, exact product identifiers or normalized product names, then vendor-level unmatched evidence. Equal best scores remain ambiguous; the code does not silently choose based on crawl order.

## Allowed document hosts

- `arete.shop`
- `cdn.shopify.com`

## Evidence ledger

- `storefront_or_category`: https://arete.shop/l/national/products/category/thca-flower (observed, observed 2026-07-15T02:25:00Z)
  - The public category page inspected did not expose a clear 21+ gate or an identity-verification requirement in the retrieved representation. No checkout was attempted.
- `laboratory_index`: https://arete.shop/lab-reports (observed, observed 2026-07-15T02:25:00Z)
  - A first-party Labs navigation item resolves to a centralized lab-report page, and the flower category states products are independently tested. Product/batch matching must be derived from report labels and product context.

## Known limitations

- Age behavior may be client-side or route-dependent and remains uncertain.
- Lab report labels may not expose a stable variant or batch identifier for every product.

## Maintenance trigger

Re-run the coverage verifier whenever `scripts/cloud_scan.py:SOURCES` changes. Re-research this vendor when the category route, age prompt, lab index, CDN host, product schema, or document labels change. Never upgrade an age classification to identity verification without direct first-party evidence of identity/document validation.
