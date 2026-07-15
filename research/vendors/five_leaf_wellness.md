# Five Leaf Wellness vendor compliance and lab-source report

**Vendor ID:** `five_leaf_wellness`
**Verified:** 2026-07-15T02:25:00Z
**Canonical origin:** https://fiveleafwellness.com
**Configured catalog route:** https://fiveleafwellness.com/shop/

## Research boundary

This report covers publicly reachable first-party pages and document links. It does not complete a purchase, enter checkout, create an account, upload identification, solve or bypass an access gate, or infer hidden behavior from marketing claims. A missing observation is recorded as uncertain or not observed rather than as proof of absence.

## Age-verification finding

- Classification: `uncertain`
- Provider: `none_observed`
- Scope: `uncertain`
- Finding: The retrieved public shop representation did not expose a clear age gate or identity-verification requirement.

Self-attestation is intentionally distinct from identity verification. This adapter does not click through, persist an age cookie, or interact with checkout.

## Laboratory-document finding

- COA availability: `not_observed`
- Terpene availability: `not_observed`
- Finding: No first-party COA, lab-report, or terpene-report link was observed on the inspected shop representation.

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

- `fiveleafwellness.com`
- `www.fiveleafwellness.com`

## Evidence ledger

- `storefront_or_category`: https://fiveleafwellness.com/shop/ (observed, observed 2026-07-15T02:25:00Z)
  - The retrieved public shop representation did not expose a clear age gate or identity-verification requirement.

## Known limitations

- Current public shop output did not expose qualifying flower products or lab links.
- Product-level pages may differ and require future safe refreshes.

## Maintenance trigger

Re-run the coverage verifier whenever `scripts/cloud_scan.py:SOURCES` changes. Re-research this vendor when the category route, age prompt, lab index, CDN host, product schema, or document labels change. Never upgrade an age classification to identity verification without direct first-party evidence of identity/document validation.
