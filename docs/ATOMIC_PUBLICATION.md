# Atomic publication ownership

DropFinder has one production mutation owner: the `DropFinder Autonomous Cloud` workflow.

## Immutable source and scan provenance

Each release starts from the workflow event's full source commit. Every retrieval shard is stamped with that commit after the worker writes it. The merge job rejects missing, duplicate, malformed, mixed-commit, or unexpected-commit shards before catalog generation.

A release is never rebased over newer source. Immediately before committing generated data, the workflow compares `origin/main` with the source commit. If `main` advanced, the run stops and requires fresh scans from the new source.

## Coupled generation

The legacy catalog, runtime/status diagnostics, catalog-v4 manifest, compact index, vendor profiles, rejections, and every detail shard are built into one candidate tree. The candidate must pass:

- strict JSON and publication verification;
- catalog-v4 manifest, generation, count, reference, and SHA-256 closure verification;
- zero-degraded runtime checks;
- absolute product and active-source floors;
- relative continuity checks against the currently published rollback generation.

Normal churn is allowed. A product or active-source collapse beyond 30 percent is rejected. An intentional retirement can proceed only through a manual dispatch with a non-trivial recorded reason; the reason and anomaly measurements are preserved in the receipt.

## Main and Pages publication

Generated data is committed to `main` with a normal fast-forward push. The complete candidate tree is then committed on top of the current `gh-pages` commit and pushed normally. Force push, orphan reconstruction, rebase, and parallel deployers are prohibited.

The public endpoint must return the same catalog-v4 generation as the candidate. Endpoint evidence records status, content type, content length, SHA-256, and cache headers for the application shell and primary data contracts.

## Receipt and rollback

After external verification, `deployment/release.json` records:

- source commit;
- generated-data commit;
- publication commit;
- workflow and run ID;
- public URL and generation ID;
- legacy product, catalog-v4 product, variant, and active-source counts;
- zero-degraded state;
- every catalog-v4 manifest-reference hash;
- continuity decision and any audited override;
- endpoint verification evidence;
- previous `gh-pages` commit as the rollback target.

Rollback means restoring the recorded `rollback_commit` as a new normal descendant commit on `gh-pages`, verifying the complete publication, and recording a new receipt. History is not rewritten.
