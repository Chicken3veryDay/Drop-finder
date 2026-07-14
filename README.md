# DropFinder OS v9.0

DropFinder is a THCA flower-only product intelligence system with strict classification, normalized catalog data, source-health monitoring, drift detection, evidence-backed certification, and self-healing extraction controls.

## Phone deployment

The credential-free cloud dashboard is published at:

**https://raw.githack.com/Chicken3veryDay/Drop-finder/main/index.html**

Open that URL in Safari or Chrome. On iPhone, use **Share → Add to Home Screen** to install it like an app.

This deployment is served from the public `main` branch through a repository CDN. It does not require a computer, VM, payment method, cloud credentials, SSH key, domain, or personal access token from the user. Changes committed to `index.html`, `cloud_site/`, or `cloud_site/data/status.json` are reflected by the deployment.

The deployment record is stored at `deployment/cdn.json`.

## What cloud mode provides

Cloud mode is a continuously hosted, read-only reliability dashboard. It currently publishes the 35-source inventory, enabled state, certification state, and bounded source-health snapshot.

It intentionally does not expose raw response bodies, cookies, request headers, authorization data, SQLite databases, queue records, runtime keys, evidence bodies, or operator logs.

Transport reachability is not treated as live source certification, and uncertified sources remain fail-closed.

## Full application boundary

A static CDN cannot run the persistent FastAPI service, worker pool, scheduler, encrypted evidence store, queue, browser processes, or SQLite writer. Those are part of the complete DropFinder v9 application package and require an actual Python host. The credential-free deployment therefore provides phone access to the cloud dashboard rather than pretending a static site is a permanent Python server.

The repository contains the cloud deployment, deployment workflows prepared for GitHub Pages, and source-package bootstrap material. GitHub Actions did not execute connector-created workflows in this repository, so the verified deployment path is the repository CDN URL above; the Pages workflow remains available for later activation.

## Future updates

The ChatGPT GitHub integration has administrator-level write access to this repository. Future changes can be made through branches or direct commits, reviewed through GitHub, and published by updating the cloud files on `main`. No new connection details are required.

## Repository

`Chicken3veryDay/Drop-finder`
