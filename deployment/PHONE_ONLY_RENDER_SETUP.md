# DropFinder phone-only Render handoff

The original Hugging Face Docker deployment was blocked by a provider-side free-tier change requiring a Pro subscription. The valid Hugging Face write token and private `Cgptmichaccount/dropfinder-private-state` dataset remain in use only for durable state persistence.

No computer, payment method, repository upload, manual web-service creation, database setup, domain, SSH key, or Docker command is required.

## 1. Create the free Render account

From a phone browser, create a personal Render account. Signing in with GitHub is acceptable.

## 2. Create one Render API key

In the Render dashboard:

1. Open the account menu.
2. Open **Account Settings**.
3. Find **API Keys**.
4. Create a new key named `dropfinder-deploy`.
5. Copy it immediately. Render displays the complete key only at creation.

## 3. Store it as a GitHub Actions secret

In `Chicken3veryDay/Drop-finder`, open:

**Settings → Secrets and variables → Actions → Secrets → New repository secret**

Create exactly:

- Name: `RENDER_API_KEY`
- Value: the Render API key

Do not replace or remove the existing `HF_TOKEN` or `DROPFINDER_OPERATOR_TOKEN` secrets.

Do not paste the API key into chat, an issue, a commit, an ordinary GitHub variable, or any source file.

## 4. Deployment handoff

After the secret appears in the Actions secrets list, report only:

`Render secret saved`

The prepared workflow then:

1. discovers the Render workspace from the API key;
2. creates or repairs a free Docker web service named `dropfinder-os`;
3. configures the public repository and production Dockerfile;
4. installs private runtime secrets;
5. deploys and waits for Render to report the build live;
6. checks `/health` and `/ready`;
7. starts or observes a real hosted storefront scan;
8. requires a consistent strict-flower catalog and zero degraded active sources;
9. records the verified URL in `deployment/render-deployment.json`.

The source package has already passed compilation and worker/sanitizer self-tests in GitHub Actions.
