# DropFinder OS v9.0 Autonomous Cloud

DropFinder is a credential-free product-intelligence system and static phone-friendly PWA. The current autonomous publication supports multiple explicitly classified product types, including cannabis flower and cannabis vape records. Controlled-category records are published only as informational metadata with purchase routes removed.

## Live phone app

**https://chicken3veryday.github.io/Drop-finder/**

This GitHub Pages address is the canonical live URL. Open it in Safari or Chrome. On iPhone, use **Share → Add to Home Screen** to install it like an app.

The deployed artifact is an isolated `gh-pages` publication branch containing the catalog, filters, sorting, favorites, source-health drawer, web-app manifest, service worker, and offline cache. It requires no user computer, VM, payment method, cloud account, API credential, SSH key, domain, personal access token, or manually supplied secret.

## Autonomous runtime

The production workflow runs six retrieval shards every three hours and on relevant code changes. Each shard performs real public-storefront requests, bounded retries for transient responses, route aggregation, product-detail verification, price and stock retrieval, and type-specific classification. The publisher runs only after every shard completes.

The admission controller then:

1. Admits only current records that satisfy the configured product-type contract, source requirements, and public-data validation gates.
2. Requires explicit product-level evidence for the classified type. Category context alone cannot satisfy the product contract.
3. Rejects unsupported forms, generic fragments, missing required evidence, stale availability, invalid prices, and other records that do not satisfy the active taxonomy.
4. Removes purchase routes from controlled-product records before public publication.
5. Quarantines failed source candidates and records product-level rejections instead of presenting them as healthy active data.
6. Writes catalog, status, runtime, quarantine, and rejection artifacts.
7. Publishes the validated tree atomically to `gh-pages`, then re-reads that branch and verifies the publication invariants.

## Current production state

Production counts, source health, product-type totals, route outcomes, and quarantine reasons change with every successful autonomous publication. The generated artifacts are authoritative:

- [`cloud_pages/data/status.json`](cloud_pages/data/status.json) contains the latest product count, product-type totals, enabled and quarantined source counts, route health, limitations, and service state.
- [`cloud_pages/data/runtime.json`](cloud_pages/data/runtime.json) contains the public runtime receipt for the current publication.
- [`cloud_pages/data/catalog.json`](cloud_pages/data/catalog.json) contains the normalized public catalog.
- [`cloud_pages/data/quarantine.json`](cloud_pages/data/quarantine.json) contains current source-candidate failures.
- [`cloud_pages/data/rejections.json`](cloud_pages/data/rejections.json) contains product-level rejection evidence.

Do not treat counts copied into issues, pull requests, or older commits as the current production state. Use the generated status artifact or the live app.

## Accuracy and privacy boundary

Every published record carries normalized classification evidence appropriate to its product type, plus provenance needed to audit the public result. The final sanitizer independently rechecks each row before persistence. Failed candidates and rejected products are recorded separately rather than silently discarded or mislabeled.

Only normalized public catalog fields, bounded evidence summaries, and aggregate health are published. Raw response bodies, cookies, request headers, authorization data, local databases, queue internals, runtime keys, retained evidence bodies, and operator logs are not published. Controlled-product records do not expose public purchase URLs.

## Hosting boundary

This credential-free design uses scheduled, resumable GitHub Actions workers and an immutable static/PWA publication branch. It is not a continuously resident FastAPI process. A permanent API daemon, browser pool, encrypted evidence service, or writable SQLite server would require a real host account or machine credentials. The current design provides autonomous retrieval, validation, persistence through Git, and an always-accessible phone interface without asking the user for any credentials.

## Deployment records

- [`deployment/autonomous-runtime.json`](deployment/autonomous-runtime.json) contains the latest worker runtime receipt.
- [`deployment/cdn.json`](deployment/cdn.json) identifies the public publication and verified blob hashes.
- [`cloud_pages/data/status.json`](cloud_pages/data/status.json) contains active service and source health.
- [`cloud_pages/data/quarantine.json`](cloud_pages/data/quarantine.json) contains failed source candidates.
- [`cloud_pages/data/rejections.json`](cloud_pages/data/rejections.json) contains product-level rejection evidence.
- [`docs/REPOSITORY_MAINTENANCE.md`](docs/REPOSITORY_MAINTENANCE.md) is the canonical future-update and rollback guide.

## Repository

`Chicken3veryDay/Drop-finder`
