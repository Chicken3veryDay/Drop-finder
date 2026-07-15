# DropFinder OS v9.0 Autonomous Cloud

DropFinder is a THCA flower-only product intelligence system with real storefront retrieval workers, product-level evidence verification, strict form rejection, source admission, normalized catalog data, source-health reporting, and atomic phone-app publication.

## Live phone app

**https://chicken3veryday.github.io/Drop-finder/**

This GitHub Pages address is the canonical live URL. Open it in Safari or Chrome. On iPhone, use **Share → Add to Home Screen** to install it like an app.

The deployed artifact is an isolated `gh-pages` publication branch containing the product catalog, filters, sorting, favorites, source-health drawer, web-app manifest, service worker, and offline cache. It requires no user computer, VM, payment method, cloud account, API credential, SSH key, domain, personal access token, or manually supplied secret.

## Autonomous runtime

The production workflow runs six retrieval shards every three hours and on relevant code changes. Each shard performs real public-storefront requests, bounded retries for transient responses, route aggregation, product-detail verification, price retrieval, and strict classification. The publisher runs only after every shard completes.

The admission controller then:

1. Admits only sources whose current workers returned qualifying products with valid product URLs and real prices.
2. Requires product-level evidence for both THCA and flower. Category context alone cannot satisfy the product contract.
3. Rejects pre-rolls, joints, blunts, concentrates, vapes, edibles, seeds, subscriptions, samplers, bundles, alternate-cannabinoid-only products, generic fragments, and other non-flower forms.
4. Quarantines failed candidates instead of publishing them as degraded active services.
5. Writes catalog, status, runtime, quarantine, and product-rejection records.
6. Publishes the validated tree atomically to `gh-pages`, then re-reads that branch and verifies the zero-degraded and evidence invariants.

## Current verified production state

Generated **2026-07-14 11:28:58 UTC**:

- **273** accepted THCA-flower products
- **12** active sources
- **12** healthy sources
- **0** degraded active sources
- **14** healthy retrieval routes
- **5** quarantined candidates
- **1** rejected non-flower product
- **6** retrieval shards
- Retrieval workers, admission controller, product sanitizer, catalog merge, and publisher all report `healthy`

The currently active sources are Black Tie CBD, Crysp, Green Unicorn Farms, Hello Mary, Holy City Farms, Loud House Hemp, Lucky Elk, Pure Roots Botanicals, Quantum Exotics, Sherlocks Glass & Dispensary, Smoky Mountain CBD, and Stoney Branch Farms.

The five quarantined candidates are not counted as active services: Arete currently blocks GitHub-hosted requests with HTTP 403 after bounded retries; Five Leaf currently exposes no qualifying flower products; Preston's rendered listing does not expose product-level THCA evidence and canonical product links to the worker; Secret Nature's configured collection is empty and its old flower routes return 404; WNC's category shell does not expose product records that pass product-detail verification.

## Accuracy and privacy boundary

Every published product carries classification evidence recording explicit THCA and flower signals plus an evidence hash. The final sanitizer independently rechecks every row before persistence. Failed candidates and rejected products are recorded separately rather than silently discarded or mislabeled.

Only normalized public catalog fields, evidence summaries, and aggregate health are published. Raw response bodies, cookies, request headers, authorization data, local databases, queue internals, runtime keys, retained evidence bodies, and operator logs are not published.

## Hosting boundary

This credential-free design uses scheduled, resumable GitHub Actions workers and an immutable static/PWA publication branch. It is not a continuously resident FastAPI process. A permanent API daemon, browser pool, encrypted evidence service, or writable SQLite server would require a real host account or machine credentials. The current design provides autonomous retrieval, validation, persistence through Git, and an always-accessible phone interface without asking the user for any credentials.

## Deployment records

- `deployment/autonomous-runtime.json` contains the latest worker runtime receipt.
- `deployment/cdn.json` identifies the public publication and verified blob hashes.
- `cloud_pages/data/status.json` contains active service and source health.
- `cloud_pages/data/quarantine.json` contains failed source candidates.
- `cloud_pages/data/rejections.json` contains product-level rejection evidence.
- `docs/REPOSITORY_MAINTENANCE.md` is the canonical future-update and rollback guide.

## Repository

`Chicken3veryDay/Drop-finder`
