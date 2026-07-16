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

## Authoritative production state

Production counts, active-source membership, route health, quarantine reasons, and rejection totals change with each publication. The README intentionally does not copy those fast-changing snapshot values.

Use the generated records as the source of truth:

- `cloud_pages/data/status.json` reports current source, route, product, rejection, and service health with its `generated_at` timestamp.
- `deployment/autonomous-runtime.json` reports the current worker receipt, shard count, product totals, and zero-degraded status.
- `cloud_pages/data/quarantine.json` records every currently quarantined candidate and its evidence-backed reason.
- `cloud_pages/data/rejections.json` records current product-level rejection evidence.
- `deployment/cdn.json` identifies the exact public publication and verified blob hashes.

The live GitHub Pages app is published from the same validated generation. Historical counts or source-specific failure explanations belong in immutable deployment records, not in this continuously reused overview.

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
