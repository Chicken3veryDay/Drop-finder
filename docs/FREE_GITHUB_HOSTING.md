# Free GitHub-Only Hosting

DropFinder's credential-free cloud mode uses GitHub Pages and GitHub-hosted Actions.

## Phone access

Open:

`https://chicken3veryday.github.io/Drop-finder/`

The page is a mobile-friendly, read-only snapshot. It remains available without a personal computer running.

## Refresh model

`.github/workflows/dropfinder-cloud.yml` runs every six hours and can also be started manually. It installs DropFinder on an isolated GitHub-hosted runner, performs a bounded collection attempt, exports only sanitized normalized product fields, and deploys the result to GitHub Pages.

The published artifact excludes raw evidence, cookies, request headers, databases, runtime keys, operator tokens, and environment files.

## Future updates

The ChatGPT GitHub connection has write access to this repository. Future maintenance can be performed through branches, pull requests, commits, CI inspection, and workflow reruns without copying the project back to a personal computer.

## Important boundary

GitHub Pages is static hosting. It does not keep the FastAPI server, scheduler, queue workers, or browser workers continuously running. Those components remain in the repository for a future authenticated server deployment. The free GitHub-only mode provides an always-available dashboard refreshed by scheduled cloud jobs rather than an interactive persistent backend.

## Public repository tradeoff

This repository is public so GitHub Pages and standard GitHub-hosted Actions can operate without a paid hosting account. Do not commit private keys, access tokens, cookies, retained evidence, databases, or `.env` files.
