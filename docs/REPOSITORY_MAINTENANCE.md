# DropFinder Repository and Deployment Maintenance

Canonical repository: `Chicken3veryDay/Drop-finder`

## Live application

The credential-free progressive web application is served from the generated `gh-pages` branch at:

`https://chicken3veryday.github.io/Drop-finder/`

Do not advertise `raw.githack.com`, raw GitHub file URLs, or another CDN wrapper as the live application URL. Those addresses can cache an obsolete publication independently of the current Pages branch and service-worker namespace.

## Authoritative release model

There is one supported serialized publication path: `.github/workflows/dropfinder-cloud.yml` (`DropFinder Autonomous Cloud`). It owns retrieval, candidate generation, continuity validation, generated-data persistence, `gh-pages` publication, public endpoint verification, and the canonical receipt.

The workflow enforces:

- immutable source checkout at the triggering `main` SHA;
- shard provenance bound to that source commit;
- read-only permissions outside the publication job;
- one repository-wide `dropfinder-pages-publication` lock with cancellation disabled;
- a compare-and-swap guard before generated artifacts can update `main`;
- one coupled legacy and Catalog V4 candidate;
- strict JSON, schema, manifest, content-hash, continuity, and zero-degraded checks before publication;
- a normal fast-forward commit to `gh-pages`, never a force push or arbitrary file copy;
- public generation verification before a receipt can be committed;
- immutable action release pins for the publication dependency boundary.

Do not add a second deployer, recovery publisher, issue-triggered writer, or manual Pages mutation path. A recovery must use the same serialized workflow and validation gates.

## Determine what is actually live

Use all three layers together:

1. `main:deployment/release.json` for source, generated, publication, rollback, workflow, URL, generation, counts, and verified endpoint identity.
2. The exact `gh-pages` commit named by that receipt.
3. The public HTTP responses from the canonical URL, fetched without relying on a browser cache.

The current release is coherent only when:

- the receipt's `publication_commit` equals the current `gh-pages` tip;
- the receipt's `generated_commit` is reachable from `main`;
- the legacy `catalog.json`, `status.json`, and `runtime.json` share the receipt's `generated_at` identity;
- the Catalog V4 manifest, compact index, and detail shards share the receipt's `generation_id`;
- all manifest and app-shell hashes match exact bytes;
- the public files match the committed `gh-pages` bytes;
- the receipt reports `zero_degraded: true` and the live status agrees.

`main:cloud_pages/` is the generated candidate retained with source history. It does not prove publication by itself. Historical files such as `deployment/cdn.json`, `deployment/pages.json`, or earlier diagnostics are evidence for their recorded runs only; they do not supersede `deployment/release.json`.

## Branch responsibilities

- `main` is the authoritative source, generated-data history, documentation, workflow, and receipt branch.
- `gh-pages` is generated publication output. Never edit it manually.
- A normal feature, repair, verification, or documentation branch must be based on current `main` and disposed after merge or documented supersession.
- A protected recovery branch or tag must identify the exact retained incident and rollback purpose. Do not keep unexplained temporary, trigger, probe, or repointed branches.

Before deleting a branch, prove that no open pull request, active workflow, environment, release, or tag depends on it and that every required unique commit is reachable from `main`, `gh-pages`, a retained PR, or a documented recovery reference.

## Product and publication boundaries

The generated catalog has type-specific contracts for supported flower, vape, and informational mushroom records. Cannabis edibles are retired from the stable taxonomy and UI. Reintroduction requires a versioned schema and migration rather than relabeling old offers.

Vape publication requires explicit positive finite milliliter quantity, `quantity_unit: ml`, and positive finite `price_per_ml`. Mass-only vape offers must be rejected as `unsupported_vape_mass_quantity`; grams must never be inferred as milliliters.

All JSON input and publication boundaries reject non-finite numbers, including nested NaN and positive or negative infinity. Product URLs, document URLs, image bytes, HTML, service-worker caches, and generated paths remain subject to the repository's normalization, SSRF, host, decode, sanitization, integrity, and scope checks.

## Change and release procedure

1. Refresh `main`, `gh-pages`, open PRs/issues, active workflow runs, branch protection, environments, releases, and the branch graph.
2. Create a branch from current `main`; do not transplant a stale full file or bypass an existing reviewed implementation.
3. Preserve type contracts, provenance, variants, lot/batch/document scope, rejection diagnostics, strict JSON, URL restrictions, and the serialized publication model.
4. Run focused regressions, the complete relevant suite, lint, type checking, production build, publication verification, and browser coverage for UI, document, query, cache, or service-worker changes.
5. Inspect every changed file and generated diff. Remove temporary builders, runners, triggers, probes, and workflow files before opening the implementation PR.
6. Require the normal exact-head workflows to pass. Do not merge a draft, a stale transplant, or a candidate with missing or failing required checks.
7. After merge, observe `DropFinder Autonomous Cloud` through retrieval, candidate generation, compare-and-swap, Pages publication, public verification, and receipt creation.
8. Verify the receipt, branch tips, endpoint graph, hashes, schemas, generation identities, source/product counts, and zero-degraded result.
9. Run the supported live browser matrix across desktop Chromium, Firefox, WebKit, mobile Chromium, and mobile WebKit for a production-affecting release.
10. Close artifact- or production-gated issues only after their generated and public evidence exists. Record exact commits, workflow run IDs, commands, browser counts, artifact digests, and rollback target.
11. Delete merged, superseded, abandoned, and temporary branches only after the reachability and dependency proof described above.

## Rollback

The canonical receipt records the previous `gh-pages` tip as `rollback_commit`. A rollback is a coherent release operation, not a manual branch edit:

1. identify the intended source/generated snapshot and the receipt being rolled back;
2. revert or repair the source on `main` through a reviewed PR;
3. run the authoritative publication workflow under the repository-wide lock;
4. allow it to build and validate one complete candidate;
5. fast-forward `gh-pages` through the normal publication step;
6. verify public generation convergence and commit a new receipt.

Do not force-push `main` or `gh-pages`, copy selected production files by hand, or restore only part of a generation.

## Security rules

Never commit operator tokens, cookies, authorization headers, private evidence bodies, runtime encryption keys, SQLite databases, queue state, or local logs. Keep workflow permissions least-privilege, pin adopted actions immutably, treat forked PR content as untrusted, and never interpolate issue titles, branch names, generated records, or external URLs into executable shell without a bounded interface.

The published tree must contain only normalized public fields, canonical safe URLs, bounded provenance and rejection summaries, deterministic generated bytes, and verified assets. No local path, secret, machine timestamp outside the defined generation contract, or nondeterministic environment data may leak into publication.

## Access for future ChatGPT maintenance

The connected GitHub integration has write access to this repository. Future maintenance should inspect current repository and production state before editing, use reviewed PRs, and preserve the single authoritative publisher. The deployment requires no personal infrastructure details from the user.
