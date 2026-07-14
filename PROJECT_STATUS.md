# DropFinder OS Repository Status

Repository: `Chicken3veryDay/Drop-finder`

## Current checkpoint

- The validated DropFinder OS v9.0 source archive exists outside this repository as `dropfinder_os_v9_0_github_ready.zip` and `dropfinder_os_v9_0_initial.bundle`.
- The repository contains a mixture of deployment work, selected v9 modules, generated static data, and remnants of an incomplete bootstrap upload under `bootstrap/`.
- The `bootstrap/source.part*.b64` files are **not** the canonical source tree and must not be treated as a usable application checkout.
- The intended zero-credential deployment is a read-only GitHub Pages dashboard refreshed by scheduled GitHub Actions scans. GitHub Pages cannot host the persistent FastAPI/worker runtime.
- No cloud credentials, payment details, Oracle account, Tailscale account, or personal server are required for the static dashboard mode.
- The next implementation thread must recover the canonical archive, compare it with the current branch, review and reconcile the repository section by section, commit each reviewed section separately, then validate and deploy.

## Safety rules

1. Work only in `Chicken3veryDay/Drop-finder`.
2. Do not modify `Chicken3veryDay/Agent---ChatGPT`.
3. Do not commit secrets, `.env` files, databases, evidence bodies, cookies, tokens, runtime queues, logs, browser profiles, virtual environments, caches, build caches, or test runtime output.
4. Do not claim the app is deployed until the Pages URL returns the expected dashboard and its latest data artifact.
5. Preserve fail-closed source certification. Static dashboard publishing must never bypass classification or source-certification gates.
6. Keep the full server application in the repository even though Pages hosts only the static dashboard.
7. Treat existing generated catalog/status files as untrusted until regenerated from reviewed code.

## Required final state

- Canonical source reconciled as normal files, not encoded bootstrap chunks.
- Partial `bootstrap/source.part*.b64` files removed after successful import verification.
- Existing autonomous/deployment scripts reviewed rather than blindly retained.
- Section-by-section commits with validation evidence.
- Full static and test gates green.
- GitHub Pages workflow committed and passing.
- Repository README contains the live phone URL and clearly describes static-dashboard limitations.
