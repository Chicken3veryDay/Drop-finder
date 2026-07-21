# Final Production Closure

## Disposition

DropFinder's canonical GitHub Pages release is live and verified. The service-worker generation-activation races discovered during fresh-profile acceptance were repaired in ordinary pull requests, validated by the full repository CI and browser suites, published through the canonical autonomous workflow, and reverified against the public deployment.

Canonical public URL:

- `https://chicken3veryday.github.io/Drop-finder/`

The authoritative machine-readable record is [`deployment/release.json`](../deployment/release.json).

## Immutable release identity

| Role | Commit / identity |
| --- | --- |
| Source commit | `6de28012090017a898be1d51f650e9ee0fc96aeb` |
| Generated-data commit | `95d85e4b0121f1f4c69d20d1d8f3d3b614cc29b0` |
| Publication commit / `gh-pages` head | `4b98724efcce4d5c47af044ec87b95a685c5757d` |
| Canonical receipt commit | `71d8deb67aa89a6355049022ebdee26d45aab149` |
| Rollback publication commit | `7e21ee3cc3da1c9219f3ba8b22c2c9a369aaabca` |
| Generation ID | `d51dd07e082c696af11f14c3c6ee1f84` |
| Generated at | `2026-07-21T00:08:08+00:00` |

## Activation-race repairs

Two independent races were fixed:

1. Prepared snapshots previously shared one metadata record. Concurrent legacy and Catalog V4 preparation could overwrite the requested generation before activation. The worker now stores prepared metadata per generation, serializes activation, retains other prepared caches during cleanup, and reads the historical singleton record for backward compatibility.
2. A fresh client could request activation before preparation completed. The coordinator now treats `generation_incomplete` as a transient preparation state and retries after 100 milliseconds within the existing ten-second activation deadline. Other generation errors remain terminal.

Implementation history:

- PR `#409`, merged as `b3c445a3effd288578da3d253a813eaa0ec4ae6f`;
- PR `#413`, merged as the canonical source commit `6de28012090017a898be1d51f650e9ee0fc96aeb`.

Both repairs include deterministic regression coverage. PR `#413` passed the autonomous validation workflow and the full Cloud CI matrix, including the complete Playwright browser job, at immutable head `5344f07f4414a7650d946bfa01eee466b1bd8f26`.

## Publisher evidence

- Workflow: `DropFinder Autonomous Cloud`
- Canonical no-override run: `29789253242`
- Result: success
- Retrieval workers: all six shards succeeded
- Atomic publisher job: success
- Atomic publication artifact: `atomic-publication-evidence-29789253242`
- Artifact ID: `8479671780`
- Artifact digest: `sha256:be003914682e95cdb3a7875b0bd34d9ec8de216ff5f788c60fb1d52c6e2c551d`

The first merge-triggered candidate was correctly rejected by the continuity gate after a transient source returned an empty collection. No override was used. A fresh complete scan then passed the same fail-closed gate and produced the canonical release above.

## Accepted production population

The canonical receipt records:

- 930 legacy catalog rows;
- 203 Catalog V4 products;
- 421 in-stock variants;
- 17 active healthy sources;
- zero degraded sources.

Continuity status is `accepted`, the anomaly list is empty, the override reason is blank, and `override.used` is `false`. Recorded drops versus the prior release were:

- legacy catalog: `0.104046`;
- Catalog V4 products: `0.125`;
- Catalog V4 variants: `0.142566`;
- active sources: `0.0`.

All were below the configured `0.3` continuity limit.

These counts describe this immutable closure generation. Current autonomous runs may publish newer counts; [`deployment/release.json`](../deployment/release.json) remains authoritative.

## Public endpoint verification

The canonical receipt verifies the public index, application shell, legacy catalog, status, runtime, Catalog V4 manifest and index, web-app manifest, and service worker. Each recorded endpoint returned HTTP 200 and matched the published SHA-256 identity.

The deployed service worker hash for this release is:

- `sha256:97e07c3f71500d32d4add538e27cd75af2639a29c5f83cc978c82dc4d301bb74`

## Fresh-profile browser acceptance

Final live acceptance run: `29790020476`.

The run created independent fresh profiles for:

- desktop Chromium;
- desktop Firefox;
- desktop WebKit;
- Pixel 7 emulation;
- iPhone 14 emulation.

Each profile verified:

- the public worker contains the generation-isolation repair;
- the manifest is bound to generation `d51dd07e082c696af11f14c3c6ee1f84`;
- runtime health is healthy with zero degraded active services;
- the service worker reports the exact generation as active;
- the current accessible result list renders;
- no terminal generation error or activation-failure banner appears;
- no uncaught page error occurs.

Final aggregate: five passed, zero failed, zero skipped, zero timed out, and zero interrupted.

Retained evidence:

- Artifact: `live-service-worker-activation-evidence-v5`
- Artifact ID: `8479909056`
- Digest: `sha256:d2694c1966eae75764ae170133bb30f41ac3c04cfe70c024be5d162f604d6d15`
- Retention expiry: `2026-10-19T00:20:55Z`

## Rollback

Rollback is publication-only and must not rewrite source history:

1. Preserve the current receipt, failed-run evidence, and incident record.
2. Confirm that rollback publication commit `7e21ee3cc3da1c9219f3ba8b22c2c9a369aaabca` is the intended previously verified state.
3. Restore `gh-pages` through the controlled release procedure without force-pushing generated source history.
4. Verify the public index, app shell, catalog, status, runtime, Catalog V4 manifest and index, service worker, and referenced hashed assets.
5. Record a new canonical receipt on `main` identifying the rollback source, publication, reason, and verification result.

Do not bypass continuity checks or publish an unreceipted tree.

## Maintenance contract

Future releases must preserve these invariants:

- one immutable source commit owns every retrieval shard;
- all configured shards complete before publication;
- generated data reaches `main` by compare-and-swap without rebasing another run's output;
- `gh-pages` advances only to a fully validated publication tree;
- prepared generation metadata remains isolated by generation;
- transient incomplete activation stays bounded by the coordinator deadline;
- the public generation is externally verified before closure;
- continuity exceptions require an explicit audited reason;
- failed candidates remain quarantined rather than represented as healthy production data.
