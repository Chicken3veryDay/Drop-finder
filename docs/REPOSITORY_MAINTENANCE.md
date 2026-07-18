# DropFinder Repository and Deployment Maintenance

Canonical repository: `Chicken3veryDay/Drop-finder`

## Live phone application

The credential-free phone application is served from the current generated `gh-pages` branch through the repository's canonical GitHub Pages URL:

`https://chicken3veryday.github.io/Drop-finder/`

Do not advertise `raw.githack.com` or other raw-file CDN wrappers as the live application URL. They may cache an obsolete publication independently of the current `gh-pages` branch.

### Determine what is actually live

Use the current `gh-pages` tree, especially `data/status.json` and `data/runtime.json`, to inspect the static files currently offered to phone clients. Files under `main:cloud_pages/` are the latest admitted source snapshot for a publisher and can be newer than, or temporarily different from, the live branch.

Deployment receipts are writer-specific evidence, not an independent universal source of truth:

- `deployment/cdn.json` is written after the autonomous publisher verifies its own `gh-pages` publication.
- `deployment/pages.json`, `deployment/pages-branch-receipt.json`, and `deployment/pages-diagnostics.json` are written by the separate Pages deployment and recovery paths when those paths run.
- `deployment/autonomous-runtime.json` describes the latest admitted autonomous snapshot on `main`; it does not by itself prove that snapshot is live.

Before treating a receipt and repository snapshot as synchronized, verify that its timestamp, publication identity, generation or catalog counts, and referenced branch state still agree with the current `gh-pages` files. Another publisher may have updated the public branch afterward.

The repository currently has multiple workflows capable of changing GitHub Pages or `gh-pages`. Until the shared publication lock and stale-generation ownership guard in [issue #102](https://github.com/Chicken3veryDay/Drop-finder/issues/102) are resolved, never infer live state from a `main` snapshot or a single writer's receipt alone.

## Branch responsibilities

- `main` — authoritative autonomous cloud source, retrieval workers, admission controller, normalized catalog state, documentation, and GitHub Actions workflows.
- `gh-pages` — generated publication output. Never edit this branch manually.
- `full-source` — reserved compatibility branch. It currently follows the validated `main` source and must not contain bootstrap archives or encoded import chunks.

## Zero-credential deployment model

GitHub Actions performs bounded storefront retrieval on a schedule, admits only healthy normalized source results, commits runtime state, and publishes generated output to GitHub Pages. The public static application remains available without the user's PC running and without Oracle, Tailscale, payment credentials, cloud API keys, or a persistent private server.

This is a static progressive web application backed by scheduled GitHub Actions snapshots. It is not a continuously running FastAPI daemon. Do not claim live mutation APIs, local SQLite access, or persistent background workers through the phone URL.

## Future update procedure

1. Read `README.md`, this document, the relevant deployment receipts, and every workflow capable of writing the affected `main`, `gh-pages`, or Pages state.
2. Refresh both `main` and `gh-pages`; never patch `gh-pages` manually.
3. Check issue #102 and active workflow runs before publishing. Do not start an overlapping writer against the same public state.
4. Make source changes on an isolated branch based on current `main`.
5. Preserve workflow permissions, concurrency fencing, per-source timeouts, sanitizer rules, zero-degraded admission, and publication verification.
6. Run the affected Python and frontend tests, compile or type checks, and publication verifiers before committing.
7. Observe the selected publisher through completion, including its final branch or Pages update and receipt step.
8. Fetch the resulting `gh-pages` state and verify its catalog, status, runtime, generated assets, source counts, product counts, and generation identifiers agree with the publication that just completed.
9. Treat a mismatched or superseded receipt as historical evidence, not proof of the current live state. Record or repair the divergence instead of silently choosing one file.
10. Roll back by reverting the source change on `main` and republishing the intended canonical snapshot through one controlled publisher.

## Security rules

Never commit operator tokens, cookies, authorization headers, private evidence bodies, runtime encryption keys, SQLite databases, queue state, or local logs. The published catalog must contain only normalized public product fields and canonical public product URLs.

## Access for future ChatGPT maintenance

The connected GitHub integration has write access to this repository. Future maintenance should target `Chicken3veryDay/Drop-finder`, inspect current branch state before editing, and use ordinary commits rather than archive reconstruction. The deployment requires no personal infrastructure details from the user.
