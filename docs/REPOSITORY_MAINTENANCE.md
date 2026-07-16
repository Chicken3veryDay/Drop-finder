# DropFinder Repository and Deployment Maintenance

Canonical repository: `Chicken3veryDay/Drop-finder`

## Live phone application

The credential-free phone application is published from the generated `gh-pages` branch and served through the repository's canonical GitHub Pages URL:

`https://chicken3veryday.github.io/Drop-finder/`

Do not advertise `raw.githack.com` or other raw-file CDN wrappers as the live application URL. They may cache an obsolete publication independently of the current `gh-pages` branch.

The current publication receipt is stored in `deployment/cdn.json`. Treat that receipt, `cloud_pages/data/status.json`, and `cloud_pages/data/runtime.json` as the source of truth for deployment health.

## Branch responsibilities

- `main` — authoritative autonomous cloud source, retrieval workers, admission controller, normalized catalog state, documentation, and GitHub Actions workflows.
- `gh-pages` — generated publication output. Never edit this branch manually.
- `full-source` — reserved compatibility branch. It currently follows the validated `main` source and must not contain bootstrap archives or encoded import chunks.

## Zero-credential deployment model

GitHub Actions performs bounded storefront retrieval on a schedule, admits only healthy normalized source results, commits runtime state, and atomically replaces `gh-pages`. The public static application remains available without the user's PC running and without Oracle, Tailscale, payment credentials, cloud API keys, or a persistent private server.

This is a static progressive web application backed by scheduled GitHub Actions snapshots. It is not a continuously running FastAPI daemon. Do not claim live mutation APIs, local SQLite access, or persistent background workers through the phone URL.

## Future update procedure

1. Read `README.md`, `deployment/cdn.json`, `deployment/autonomous-runtime.json`, and `.github/workflows/dropfinder-cloud.yml`.
2. Make source changes on `main`; never patch `gh-pages` directly.
3. Preserve workflow `contents: write` permission, concurrency fencing, per-source timeouts, sanitizer rules, zero-degraded admission, and publication verification.
4. Run the affected Python self-tests and compile checks before committing.
5. Observe the autonomous workflow through completion.
6. Verify the GitHub Pages URL, new `gh-pages` catalog, status, runtime, and deployment receipt agree on product/source counts and report zero degraded active sources.
7. Roll back by reverting the source commit on `main`; the next successful workflow publication replaces the generated branch atomically.

## Security rules

Never commit operator tokens, cookies, authorization headers, private evidence bodies, runtime encryption keys, SQLite databases, queue state, or local logs. The published catalog must contain only normalized public product fields and canonical public product URLs.

## Access for future ChatGPT maintenance

The connected GitHub integration has write access to this repository. Future maintenance should target `Chicken3veryDay/Drop-finder`, inspect current branch state before editing, and use ordinary commits rather than archive reconstruction. The deployment requires no personal infrastructure details from the user.
