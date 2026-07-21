# DropFinder OS v9.0 Autonomous Cloud

DropFinder is a multi-product storefront intelligence system with real retrieval workers, product-level evidence verification, type-specific admission rules, normalized catalog data, source-health reporting, and atomic phone-app publication.

## Live phone app

**https://chicken3veryday.github.io/Drop-finder/**

This GitHub Pages address is the canonical live URL. Open it in Safari or Chrome. On iPhone, use **Share → Add to Home Screen** to install it like an app.

The deployed artifact is an isolated `gh-pages` publication branch containing the product catalog, filters, sorting, favorites, source-health drawer, web-app manifest, service worker, and offline cache. It requires no user computer, VM, payment method, cloud account, API credential, SSH key, domain, personal access token, or manually supplied secret.

## Product contract

The current catalog supports separate, type-aware records for:

- cannabis flower;
- cannabis vape products;
- psilocybin mushroom metadata for informational use only, with purchase links removed.

Each product type has its own evidence, normalization, comparison, and publication rules. Records that cannot satisfy the applicable contract are rejected or quarantined rather than being coerced into another type. The application does not infer unsafe conversions between incompatible units such as grams and milliliters.

## Autonomous runtime

The production workflows perform real public-storefront requests, bounded retries for transient responses, route aggregation, product-detail verification, price and stock retrieval, and type-specific classification. The publisher runs only after the configured retrieval shards complete.

The admission controller then:

1. Admits only sources whose current workers returned products that satisfy the relevant type contract, with valid public URLs and current prices where purchasing is permitted.
2. Requires product-level evidence rather than relying on category context alone.
3. Rejects unsupported forms and records that fail current price, stock, identity, or type-specific evidence gates.
4. Removes purchase links from informational-only product types.
5. Quarantines failed candidates instead of publishing them as degraded active services.
6. Writes catalog, status, runtime, quarantine, and product-rejection records.
7. Publishes the validated tree atomically to `gh-pages`, then verifies the published branch and zero-degraded invariant.

## Authoritative production state

The repository publishes a new runtime snapshot autonomously, so product, source, route, quarantine, and rejection counts change more frequently than this README. The generated artifacts are the authoritative current state:

- [`cloud_pages/data/runtime.json`](cloud_pages/data/runtime.json) contains the generation timestamp, product counts by type, active-source count, shard count, and zero-degraded result.
- [`cloud_pages/data/status.json`](cloud_pages/data/status.json) contains source and route health, fallback use, current limitations, product counts by type, and aggregate rejection reasons.
- [`cloud_pages/data/catalog-v4/manifest.json`](cloud_pages/data/catalog-v4/manifest.json) identifies the immutable catalog generation and its verified assets.
- [`cloud_pages/data/quarantine.json`](cloud_pages/data/quarantine.json) contains source candidates excluded from the active catalog.
- [`cloud_pages/data/rejections.json`](cloud_pages/data/rejections.json) contains product-level rejection evidence.
- [`deployment/release.json`](deployment/release.json) binds the immutable source, generated-data, publication, rollback, workflow, endpoint, and generation identities for the latest verified release.

Do not copy generated counts or vendor lists into hand-maintained documentation. Read the artifacts above or the live application's source-health surface when an exact current value is required.

## Accuracy and privacy boundary

Every published product carries type-specific evidence and normalized public fields. Final publication independently rechecks each row before persistence. Failed candidates and rejected products are recorded separately rather than silently discarded or mislabeled.

Only normalized public catalog fields, bounded evidence summaries, and aggregate health are published. Raw response bodies, cookies, request headers, authorization data, local databases, queue internals, runtime keys, retained evidence bodies, and operator logs are not published.

## Hosting boundary

This credential-free design uses scheduled, resumable GitHub Actions workers and an immutable static/PWA publication branch. It is not a continuously resident FastAPI process. A permanent API daemon, browser pool, encrypted evidence service, or writable SQLite server would require a real host account or machine credentials. The current design provides autonomous retrieval, validation, persistence through Git, and an always-accessible phone interface without asking the user for credentials.

## Reproducible tracked source

The supported server-side source boundary is the editable reliability package under `app/`. It contains strict contracts, the adapter registry, and a durable SQLite adapter store. It is intentionally smaller than the unrecoverable historical full-server archive and does not claim to provide a resident production API.

From a clean checkout:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python scripts/verify_source_boundary.py
python -m unittest discover -s tests/app -p 'test_*.py' -v
```

`.github/workflows/source-boundary.yml` runs the same package installation, import graph, and store tests in CI. The obsolete incomplete `bootstrap/source.part*.b64` fragments are not part of the build.

## Deployment and maintenance records

- [`deployment/release.json`](deployment/release.json) is the canonical machine-readable deployment receipt.
- [`docs/FINAL_PRODUCTION_CLOSURE.md`](docs/FINAL_PRODUCTION_CLOSURE.md) records the immutable release chain, retained evidence, live activation acceptance, and rollback procedure.
- `deployment/autonomous-runtime.json` contains the latest worker runtime receipt.
- `deployment/cdn.json` identifies the public publication and verified blob hashes.
- `docs/REPOSITORY_MAINTENANCE.md` is the canonical future-update and rollback guide.
- `release/source-build.json` records the supported tracked-source boundary and historical archive disposition.

## Repository

`Chicken3veryDay/Drop-finder`
