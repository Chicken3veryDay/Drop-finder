# GitHub-Only Phone Access

DropFinder OS v9 includes a zero-credential cloud mode designed for this public repository.

## Phone URL

Open:

`https://chicken3veryday.github.io/Drop-finder/`

Add that page to the phone's home screen for app-like access. The page is hosted by GitHub Pages, so the user's PC does not need to be running.

## How data is refreshed

The permanent workflow at `.github/workflows/cloud-pages.yml` runs scheduled, manually, and after relevant changes on `main`. It uses isolated scan shards with per-source timeouts, merges only normalized publishable results, builds the static dashboard, and deploys the result to GitHub Pages.

The Pages dashboard is read-only. The complete FastAPI, worker, scheduler, evidence, certification, and self-healing source code remains in this repository for full-server deployments.

## Privacy boundary

The cloud publisher must never upload raw responses, cookies, authorization headers, encrypted evidence, SQLite databases, queue records, runtime keys, or operator tokens. Only normalized public catalog fields and aggregate source-health information belong in the Pages artifact.

## Future updates

1. Make changes on a branch.
2. Run the repository test and static-analysis gates.
3. Merge to `main`.
4. GitHub Actions refreshes and republishes the phone dashboard automatically.

ChatGPT can continue to inspect and update this repository through the connected GitHub integration while that repository permission remains enabled.

## Honest limitations

GitHub Pages does not run a persistent Python API or worker. Scheduled GitHub Actions perform bounded scans and publish snapshots. Source profiles without current replay-verified live evidence remain quarantined, and a refresh may publish an empty or partial catalog rather than inventing results.
