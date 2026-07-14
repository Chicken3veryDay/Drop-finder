# DropFinder OS v9.0

DropFinder is a THCA flower-only product intelligence system with strict product classification, normalized catalog data, source health monitoring, drift detection, evidence-backed certification, and self-healing extraction controls.

## Phone app

The credential-free cloud dashboard is available at:

**https://chicken3veryday.github.io/Drop-finder/**

Open it in Safari or Chrome and add it to the phone home screen. GitHub Pages keeps the dashboard available without a PC running. GitHub Actions performs bounded public-storefront scans every six hours and republishes the normalized snapshot.

Current cloud mode is intentionally read-only. GitHub Pages cannot run the persistent FastAPI, worker, scheduler, encrypted evidence, or queue services; those remain part of the full v9 application for server deployment.

## Cloud privacy boundary

The Pages publisher includes only normalized public catalog fields and aggregate source health. It does not publish raw responses, cookies, request headers, authorization data, SQLite databases, queue records, runtime keys, or evidence bodies.

## Repository automation

- `.github/workflows/dropfinder-cloud.yml` scans and deploys the phone dashboard.
- `scripts/cloud_scan.py` is the dependency-free bounded cloud scanner.
- `cloud_pages/` is the installable offline-capable phone dashboard.
- Changes to the scanner or dashboard trigger a fresh deployment.
- Scheduled scans run every six hours.

## Accuracy rules

The cloud scanner accepts only records with flower and THCA evidence and rejects pre-rolls, vapes, edibles, concentrates, seeds, accessories, topicals, and other nonflower forms. Failed sources are shown as degraded instead of being treated as empty truth. A cloud health result is not equivalent to full v9 live-source certification.

## Local full application

The complete v9 application supports the FastAPI web service, workers, scheduler, durable queue, evidence encryption, adapter versioning, route canaries, drift incidents, certification, shadow promotion, and automatic rollback. See `docs/` for architecture, security, operations, and certification details.

## Future updates

The connected GitHub integration can inspect and update this repository directly. Normal changes should be developed on a branch, validated, merged to `main`, and then republished automatically by GitHub Actions.
