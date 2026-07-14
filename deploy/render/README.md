# DropFinder Render deployment

This package runs the autonomous DropFinder web service on a Render Free web-service instance while retaining durable catalog state in the private Hugging Face dataset repository created during the earlier hosting attempt.

## Runtime

- FastAPI mobile web application and JSON API
- strict THCA-flower storefront workers
- automatic stale-startup and three-hour scans
- authenticated **Scan now** action
- source quarantine and final product sanitizer
- private Hugging Face dataset snapshot restore and backup
- `/health` and `/ready` deployment gates

## Render configuration

The GitHub deployment workflow creates or repairs the service through the official Render API with:

- service type: `web_service`
- runtime: `docker`
- instance plan: `free`
- region: `ohio`
- Dockerfile: `deploy/render/Dockerfile`
- health check: `/health`
- automatic Git-triggered deploys disabled

A real hosted scan must complete before `deployment/render-deployment.json` is committed.

## Required GitHub Actions secrets

- `RENDER_API_KEY`
- `HF_TOKEN`
- `DROPFINDER_OPERATOR_TOKEN`

Secrets are installed as Render environment variables by the workflow and are never written to the deployment receipt.
