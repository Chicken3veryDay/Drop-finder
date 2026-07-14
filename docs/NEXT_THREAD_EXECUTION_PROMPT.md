# Fresh-thread execution prompt

Copy the text below into a new ChatGPT thread with GitHub connected.

---

Continue the DropFinder OS v9.0 repository recovery, review, validation, cleanup, and deployment in the existing public repository **Chicken3veryDay/Drop-finder**.

Do not use or modify **Chicken3veryDay/Agent---ChatGPT**.

Read `PROJECT_STATUS.md` first. The current branch is not a trusted canonical checkout. It contains deployment work, selected source modules, generated static data, and remnants of an incomplete archive bootstrap. The `bootstrap/source.part*.b64` files are not canonical application files.

Canonical artifacts from the prior thread are:

- `dropfinder_os_v9_0_github_ready.zip`
- `dropfinder_os_v9_0_initial.bundle`
- `dropfinder_os_v9_0_github_handoff.md`
- `dropfinder_os_v9_0_github_artifacts.sha256`
- `dropfinder_os_v9_0_complete_build.zip`
- `DROPFINDER_OS_V9_0_RELEASE_REPORT.md`

Locate those artifacts from the conversation or Library. Materialize the GitHub-ready ZIP into a clean working directory. Verify its SHA-256 against the checksum file before importing or replacing anything.

## Non-negotiable execution rules

1. Inspect the canonical archive and the current `main` branch before writing.
2. Compare current repository files against the canonical archive; do not overwrite reviewed newer deployment work without understanding it.
3. Scan for secrets and prohibited runtime artifacts.
4. Never commit `.env`, credentials, tokens, keys, cookies, databases, WAL/SHM files, evidence bodies, queue payloads, logs, browser profiles, virtual environments, caches, build caches, or test runtime output.
5. Review and reconcile the repository **section by section**. Make one coherent commit per section. Do not make one giant opaque source dump.
6. After each section, run the smallest relevant validation and inspect the resulting GitHub commit before continuing.
7. Do not weaken classification, persistence, fetch isolation, evidence, queue fencing, or source-certification rules to make tests pass.
8. Do not trust existing generated catalog/status JSON until regenerated from reviewed code.
9. Do not claim deployment success until the live GitHub Pages URL is reachable and displays the expected generated dashboard.
10. If GitHub Pages cannot be enabled through the available connector, commit the correct workflow and document the exact single UI action still required. Do not pretend it was enabled.
11. Preserve the complete FastAPI/worker application in source. GitHub Pages hosts only the static, read-only dashboard.
12. Update `PROJECT_STATUS.md` after every completed section with the commit SHA, tests run, and remaining work.

## Required section order

### Section 0 — Recover, verify, and compare canonical source

- Materialize the canonical GitHub-ready ZIP.
- Verify checksum.
- Inventory all files, sizes, executable bits, symlinks, and generated artifacts.
- Compare archive version metadata with the v9.0 release report.
- Compare the archive with current `main`, classifying each difference as canonical source, newer deployment work, generated output, bootstrap debris, or suspicious/unreviewed code.
- Run secret scanning and reject unsafe files.
- Produce `docs/import/00_ARCHIVE_VERIFICATION.md` and `docs/import/00_CURRENT_BRANCH_DIFF.md`.
- Commit only verification documents and safe import tooling.
- Commit message: `chore(import): verify and compare canonical v9.0 source`

### Section 1 — Repository root and packaging

Review/reconcile:

- `.gitignore`
- `.gitattributes`
- `README.md`
- license files
- `pyproject.toml`
- requirements and lock files
- CLI entry points
- release/version metadata

Validate package metadata, dependency declarations, local-path absence, secret safety, wheel, and sdist configuration.

Commit message: `build: reconcile v9 packaging and repository metadata`

### Section 2 — Core contracts and security boundary

Review/reconcile `app/core/`, authentication, authorization, cursor signing, request limits, logging, metrics foundations, and URL/network safety.

Validate compile, Ruff, mypy, API authorization inventory, and focused security tests.

Commit message: `feat(core): reconcile hardened contracts and security boundary`

### Section 3 — Storage, migrations, backup, and queue

Review/reconcile `app/storage/`, migrations, backup/restore, event/history persistence, queue/lease fencing, notification outbox, and telemetry spool.

Validate fresh/upgrade migrations, foreign keys, concurrent queue fencing, backup tamper detection, and restore behavior.

Commit message: `feat(storage): reconcile durable persistence queue and recovery`

### Section 4 — Fetching, browser isolation, and evidence

Review/reconcile HTTP fetching, Crawlee runtime, Playwright/browser worker, response cache, evidence encryption, redaction, integrity, retention, and replay.

Validate SSRF, redirects, MIME, response limits, decompression, tamper detection, redaction, and browser isolation.

Commit message: `feat(fetch): reconcile isolated fetching and encrypted evidence`

### Section 5 — Scraping, classification, normalization, and scoring

Review/reconcile source profiles, scraper/parser strategies, classification, normalization, identity, scoring, coupon lifecycle, curated corpus, and deterministic builders.

Validate source-profile generation, corpus generation, adversarial negatives, cultivar false positives, parser fixtures, and scoring tests.

Commit message: `feat(pipeline): reconcile extraction classification and scoring`

### Section 6 — v9 reliability control plane

Review/reconcile route observations, canaries, adaptive scheduling, fingerprints, certified-only baselines, drift incidents, immutable adapters, repair candidates, replay certification, shadow promotion, rollback/probation, reliability API, and metrics.

Inspect every existing `autonomous_worker*.py` and `autonomous_merge.py`; consolidate or delete superseded versions rather than retaining numbered experiments.

Validate adapter immutability, promotion generation fencing, rollback, certified-only baseline learning, request budgets, incident deduplication, and focused v9 tests.

Commit message: `feat(reliability): reconcile autonomous certification and self-healing control plane`

### Section 7 — API, workers, and operator interfaces

Review/reconcile FastAPI application/routers, scheduler, scan workers, notification dispatcher, terminal UI, web UI, and v9 source-operations dashboard.

Validate auth, storage-failure 503 mapping, Prometheus instrumentation, TUI, and bounded worker shutdown.

Commit message: `feat(app): reconcile API workers and operator interfaces`

### Section 8 — Tests, scripts, documentation, and launchers

Review/reconcile the complete test tree, build/release/validation scripts, Linux/macOS launcher, Windows launcher, Docker, security docs, and operations docs.

Validate script safety, launcher preflight, Docker static contracts, and removal of stale v8.5 claims.

Commit message: `test: reconcile validation matrix launchers and operations docs`

### Section 9 — Zero-credential GitHub Pages deployment

Audit all existing workflows before adding another. Consolidate duplicate or superseded workflows such as bootstrap, Pages repair/fallback, cloud, and deployment experiments.

The final design should have the minimum coherent workflows needed for:

- CI
- bounded scheduled scan shards
- safe static artifact merge
- GitHub Pages deployment
- manual dispatch

Requirements:

- strict timeouts
- workflow concurrency
- minimum permissions
- pinned or trusted action versions
- normalized safe output only
- no raw evidence, headers, cookies, tokens, databases, queue files, or logs in Pages artifacts
- generated catalog/status files rebuilt from reviewed code
- no workflow self-modifying `main` unless explicitly justified and fenced

Validate workflow YAML, local static build, mobile rendering, artifact contents, and triggers.

Commit message: `deploy(pages): finalize zero-credential phone dashboard`

### Section 10 — Full validation and cleanup

Run:

- Python compile
- Ruff
- full mypy
- deterministic source-profile check
- deterministic corpus check
- API authorization inventory
- complete isolated core matrix
- real Chromium browser matrix
- clean wheel installation and `pip check`
- extracted archive validation
- launcher preflight
- secret scan

Then:

- remove all `bootstrap/source.part*.b64` remnants
- remove bootstrap workflow and obsolete numbered worker scripts
- remove temporary import tools and reports containing local paths
- regenerate safe static data
- update README and `PROJECT_STATUS.md`
- produce `docs/import/10_FINAL_IMPORT_REPORT.md`

Commit message: `release: finalize reviewed DropFinder OS v9.0 repository`

## Deployment verification

After the Pages workflow succeeds:

1. Determine the actual Pages URL for `Chicken3veryDay/Drop-finder`.
2. Open it and verify HTTP success.
3. Verify the dashboard on a narrow/mobile viewport.
4. Verify generated timestamp and source summary.
5. Verify no private evidence or secrets are exposed.
6. Record workflow run, deployment commit, URL, timestamp, and limitations.

## Final response requirements

Report every section commit SHA, validation result per section, complete final test totals, live Pages URL only if independently verified, remaining limitations, and any single manual GitHub setting still required.

Do not stop after planning. Continue through every section the available tools permit. Do not inflate success claims.

---
