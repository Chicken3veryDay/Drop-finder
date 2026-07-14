# DropFinder OS v9.0

DropFinder is a THCA flower-only product intelligence system with strict classification, normalized catalog data, source-health monitoring, drift detection, evidence-backed certification, and self-healing extraction controls.

## Phone deployment

The credential-free public catalog is published at:

**https://raw.githack.com/Chicken3veryDay/Drop-finder/gh-pages/index.html**

Open that URL in Safari or Chrome. On iPhone, use **Share → Add to Home Screen** to install it like an app.

The deployed artifact is an isolated `gh-pages` publication branch built directly from the canonical `cloud_pages/` blobs. It currently contains the product catalog, filtering and sorting UI, favorites, source-health drawer, web-app manifest, icon, service worker, and offline cache. It does not require a computer, VM, payment method, cloud credentials, SSH key, domain, or personal access token from the user.

The deployment record is stored at `deployment/cdn.json`.

## Current cloud snapshot

The current credential-free snapshot was generated on 2026-07-14 at 10:24:58 UTC and contains 247 normalized products across a 35-source inventory, with 17 sources enabled and 10 reporting healthy routes.

Only normalized public catalog fields and aggregate source health are published. Raw response bodies, cookies, request headers, authorization data, SQLite databases, queue records, runtime keys, evidence bodies, and operator logs remain private.

Transport reachability is not treated as live source certification, and uncertified sources remain fail-closed.

## Full application boundary

A static CDN cannot run the persistent FastAPI service, worker pool, scheduler, encrypted evidence store, queue, browser processes, or SQLite writer. Those are part of the complete DropFinder v9 application package and require an actual Python host. The credential-free deployment therefore provides the complete static cloud catalog and monitoring interface rather than pretending a static site is a permanent Python server.

The repository contains the cloud deployment, scheduled scanner workflow, Pages deployment and repair workflows, and source-package bootstrap material. The public CDN route does not depend on those workflows completing because it serves the committed `gh-pages` branch directly.

## Future updates

The connected GitHub integration has administrator-level write access to this repository. Future cloud releases can rebuild the `gh-pages` tree directly from validated catalog blobs without requesting new connection details.

## Repository

`Chicken3veryDay/Drop-finder`
