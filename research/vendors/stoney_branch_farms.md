# Stoney Branch Farms vendor compliance and lab-source report

**Vendor ID:** `stoney_branch_farms`
**Verified:** 2026-07-15T02:25:00Z
**Canonical origin:** https://stoneybranch.com
**Configured catalog route:** https://stoneybranch.com/collections/thca

## Research boundary

This report covers publicly reachable first-party pages and document links. It does not complete a purchase, enter checkout, create an account, upload identification, solve or bypass an access gate, or infer hidden behavior from marketing claims. A missing observation is recorded as uncertain or not observed rather than as proof of absence.

## Age-verification finding

- Classification: `uncertain`
- Provider: `none_observed`
- Scope: `uncertain`
- Finding: No explicit public age gate or identity-verification mechanism was observable in the retrieved THCA collection representation.

Self-attestation is intentionally distinct from identity verification. This adapter does not click through, persist an age cookie, or interact with checkout.

## Laboratory-document finding

- COA availability: `not_observed`
- Terpene availability: `not_observed`
- Finding: No COA or lab-document link was observed on the inspected collection representation.

### First-party lab indexes

- No centralized index observed in this pass.

## Discovery and parsing strategy

- Discovery strategy: `product_page_links`
- Parser strategy: `safe_auto_structured_html_json_pdf_text`
- Product-page discovery: `true`
- Structured API discovery: `true`
- OCR: unsupported by design
- Redirect policy: `same_vendor_or_declared_cdn_hosts_only`

The adapter accepts only bounded public HTTP(S) resources on the declared host allowlist. It extracts structured JSON, structured HTML, plain text, and a deliberately limited uncompressed text-PDF subset. Scanned, encrypted, compressed-without-a-vetted-parser, or otherwise unsupported documents remain explicit unsupported records.

## Mapping contract

Documents are mapped only with explicit evidence. Ranking is deterministic: exact variant identifiers, exact batch identifiers, exact normalized weight, exact product identifiers or normalized product names, then vendor-level unmatched evidence. Equal best scores remain ambiguous; the code does not silently choose based on crawl order.

## Allowed document hosts

- `cdn.shopify.com`
- `stoneybranch.com`
- `www.stoneybranch.com`

## Evidence ledger

- `storefront_or_category`: https://stoneybranch.com/collections/thca (observed, observed 2026-07-15T02:25:00Z)
  - No explicit public age gate or identity-verification mechanism was observable in the retrieved THCA collection representation.

## Known limitations

- Collection output may omit product-page report links.
- No centralized public laboratory page was observed.

## Maintenance trigger

Re-run the coverage verifier whenever `scripts/cloud_scan.py:SOURCES` changes. Re-research this vendor when the category route, age prompt, lab index, CDN host, product schema, or document labels change. Never upgrade an age classification to identity verification without direct first-party evidence of identity/document validation.
