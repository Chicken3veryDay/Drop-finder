---
title: DropFinder OS v9 Full Stack
emoji: "🔎"
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# DropFinder OS v9 Full Stack

This Docker Space runs the complete DropFinder FastAPI interface, queue worker,
scan scheduler, reliability scheduler, Playwright browser runtime, and durable
SQLite state replication.

Required Space secrets:

- `DROPFINDER_OPERATOR_TOKEN`
- `R2_ENDPOINT_URL`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`

Optional variables:

- `R2_STATE_KEY` (default: `dropfinder/state-v1.tar.gz`)
- `DROPFINDER_WORKER_COUNT` (default: `1`)
- `DROPFINDER_BACKUP_INTERVAL_SECONDS` (default: `300`)

The operator token is entered from the **Operator** button in the web UI and is
kept only in browser session storage.
