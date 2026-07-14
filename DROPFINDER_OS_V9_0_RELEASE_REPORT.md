# DropFinder OS v9.0 Complete Build Report

Generated: 2026-07-13

## Release identity

- Version: `9.0.0`
- Python release-validation runtime: `3.13.5`
- Configured source profiles: **35**
- Generated route adapters: **93**
- Packaging outputs: wheel, source distribution, and complete source ZIP

## Implemented v9 control plane

The build contains a separate reliability control plane with durable source and route state, immutable adapter versions, generation-fenced state transitions, adaptive canaries, per-route budgets, JSON/DOM/network fingerprints, certified-only robust baselines, deduplicated drift incidents, durable healing workflows, deterministic extraction repair, replay certification, shadow comparison, promotion probation, and automatic rollback.

The trusted acceptance boundary remains deterministic. Extraction repair cannot weaken URL safety, flower classification, identity, provenance, evidence, or final persistence requirements. Browser escalation runs in a disposable process and is budgeted separately.

## Validation results

### Static gates

- Python compilation: passed
- Ruff: passed with zero findings
- Full mypy: passed with zero errors across 97 source files
- Modular source-profile generation check: passed
- Launcher preflight: passed; 35 sources and 93 routes bootstrapped

### Core matrix

- Files: 38
- Isolated pytest processes: 38
- Tests passed: **491**
- Subtests passed: **167**
- Failed: **0**
- Errors: **0**
- Skipped: **0**

### Real Chromium matrix

- Browser files: 3
- Browser tests passed: **4**
- Failed: **0**
- Errors: **0**
- Skipped: **0**
- Covered dashboards: catalog, v8 operations, and v9 source reliability operations

### Complete collected inventory

- **495 tests collected**
- **495 tests passed** (`491` core + `4` real-browser)
- **167 subtests passed**
- **0 failures, 0 errors, 0 skips**

### Packaging and runtime smoke

- Wheel built successfully
- Source distribution built successfully
- Wheel installed into a new virtual environment
- `pip check`: no broken requirements
- Clean installed package imported as version `9.0.0`
- Clean installed `/health`: 200
- Clean installed `/ready` without a worker: correctly fail-closed with 503
- Clean installed v9 operations API: 35 sources / 93 routes
- Clean installed `/metrics`: 200
- Linux launcher live smoke: API, worker readiness, v9 operations API, and Prometheus metrics passed
- Docker Compose document parsed and contains API, worker, scan scheduler, and reliability scheduler services
- Extracted release ZIP passed compilation, Ruff, full mypy, source-profile generation, launcher preflight, 49 focused v9/deployment tests, and a real-Chromium v9 dashboard test

## Supporting repository integrations

- Crawlee Python: bounded crawler orchestration
- Playwright Python: isolated browser escalation and Chromium E2E validation
- Extruct: JSON-LD, Microdata, and RDFa extraction
- Parsel: CSS/XPath extraction primitives
- DeepDiff: nested output and change-set diffs
- GenSON and JSON Schema: shape discovery and schema validation
- Tenacity: bounded retry primitives
- OpenTelemetry: reliability spans
- Prometheus FastAPI Instrumentator: HTTP metrics, with a compatibility resolver for FastAPI lazy included routers
- Hypothesis: property-based contracts

## Fail-closed source truth

This release does not label third-party storefronts live-certified without retained replay-verified evidence. Network DNS was restricted in the build environment, so live route certification was not fabricated. Uncertified routes remain governed by their static/runtime certification state.

## Environment-specific validation not executable here

- Native Windows PowerShell execution was not available in the Linux build environment. Windows launcher structure and behavior contracts are covered by automated tests, but a native Windows process smoke remains an external deployment check.
- A Docker daemon was not available. Dockerfile and Compose topology were statically tested and parsed, but an actual container runtime smoke remains an external deployment check.
- A 24-hour live soak and current third-party storefront certification require a deployed environment with outbound DNS/network access.

These are environment limitations, not hidden passing claims.
