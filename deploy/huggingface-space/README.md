---
title: DropFinder OS v9 Cloud
emoji: "🔎"
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# DropFinder OS v9 Cloud

This Docker Space runs DropFinder as a live hosted service rather than a static
snapshot. It includes:

- the strict THCA-flower storefront retrieval workers;
- product-level THCA and flower evidence requirements;
- final non-flower sanitization and source quarantine;
- a FastAPI health, readiness, catalog, status, and scan-control API;
- automatic scans every three hours;
- a mobile web interface with search, sorting, filters, favorites, source health,
  and an authenticated **Scan now** control;
- private persistent state snapshots stored in a Hugging Face dataset repository.

## Public endpoints

- `/` mobile catalog
- `/health` process health
- `/ready` catalog and source-state readiness
- `/api/catalog`
- `/api/status`
- `/api/runtime`
- `/api/quarantine`
- `/api/rejections`
- `/api/scan-state`

`POST /api/scan` requires the operator token using either
`Authorization: Bearer <token>` or `X-Operator-Token: <token>`.

## Runtime secrets

The GitHub deployment workflow installs these automatically:

- `HF_TOKEN`, used only for the private state repository;
- `DROPFINDER_OPERATOR_TOKEN`, used for mutation authorization.

No email password, payment method, Oracle account, Cloudflare account, personal
computer, SSH key, or external database is required.

The free Space may sleep after inactivity. Opening the app wakes it; restored
state remains available through the private dataset snapshot.
