# DropFinder Repository Status

Repository: `Chicken3veryDay/Drop-finder`

## Supported runtime boundaries

DropFinder has two explicit, independently testable boundaries:

1. **Static production application.** Scheduled GitHub Actions retrieve public storefront data, validate it, build immutable Catalog V4 artifacts, and publish the PWA to GitHub Pages.
2. **Tracked reliability package.** The editable `app/` package contains the supported reliability contracts, adapter registry, and durable adapter store. It is installed from `pyproject.toml` and verified from a clean checkout by `.github/workflows/source-boundary.yml`.

The repository does not claim to contain the unrecoverable historical `dropfinder_os_v9_0_complete_build.zip` archive or a continuously resident FastAPI/worker server. Complete indexed, ref, and orphan history was searched on July 19, 2026; no valid ZIP or archive matching the historical SHA-256 was found.

## Source checkout

From a clean checkout:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python scripts/verify_source_boundary.py
python -m unittest discover -s tests/app -p 'test_*.py' -v
```

The verifier compiles and imports every tracked `app` module, validates all first-party import edges, requires package metadata, and fails if obsolete encoded bootstrap fragments return.

## Deployment boundary

- Live application: `https://chicken3veryday.github.io/Drop-finder/`
- GitHub Pages hosts a static, read-only PWA. It cannot host a persistent API daemon, browser pool, writable SQLite service, or background worker process.
- No cloud credentials, payment details, personal server, API token, SSH key, or private browser profile are required for the current production mode.
- Generated catalog and health artifacts remain authoritative for current counts and source state.

## Safety rules

1. Work only in `Chicken3veryDay/Drop-finder`.
2. Do not modify `Chicken3veryDay/Agent---ChatGPT`.
3. Do not commit secrets, `.env` files, databases, evidence bodies, cookies, tokens, runtime queues, logs, browser profiles, virtual environments, caches, build caches, or test runtime output.
4. Do not claim a deployment is current until the Pages URL and its immutable publication receipt are independently verified.
5. Preserve fail-closed source certification and publication gates.
6. Keep server-side code claims limited to the modules actually tracked and tested in this repository.
7. Treat checked-in generated artifacts as untrusted until regenerated and verified by the authoritative publication workflow.
