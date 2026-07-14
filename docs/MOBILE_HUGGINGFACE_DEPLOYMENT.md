# DropFinder phone-only Hugging Face deployment

No computer, Oracle account, Cloudflare account, payment method, SSH key, domain,
or manual Space creation is required.

The deployment workflow creates:

- a public Docker Space named `dropfinder-os` under the Hugging Face account;
- a private dataset repository named `dropfinder-private-state`;
- the Space secrets and runtime variables;
- the FastAPI service, mobile interface, scheduled scraper, and private backups;
- a verified deployment receipt only after a real hosted scan passes.

## Security prerequisite

Do not reuse any password that has appeared in a chat message. Change exposed
passwords before using the associated account elsewhere.

Never paste the Hugging Face token or DropFinder operator token into a chat,
issue, commit, ordinary GitHub variable, or Space source file.

## Step 1: Create the Hugging Face account from a phone

Open Hugging Face in Safari or Chrome and create a free personal account using a
new, unique password. Record the Hugging Face username, but it does not need to
be entered into DropFinder; the deployment workflow discovers it from the token.

## Step 2: Create one Hugging Face write token

From the Hugging Face account:

1. Open the account menu.
2. Open **Settings**.
3. Open **Access Tokens**.
4. Choose **New token**.
5. Name it `dropfinder-deploy`.
6. Choose the **Write** role.
7. Create the token and copy it immediately.

This dedicated token lets the deployment workflow create and update repositories
under the account. It can be revoked later without changing the account password.

## Step 3: Add two GitHub Actions secrets

In a mobile browser, open the `Chicken3veryDay/Drop-finder` repository and go to:

**Settings → Secrets and variables → Actions → Secrets**

Add these repository secrets exactly:

### `HF_TOKEN`

Paste the Hugging Face write token created in Step 2.

### `DROPFINDER_OPERATOR_TOKEN`

Paste the separately generated DropFinder operator token. This authorizes the
mobile **Scan now** control. It is unrelated to the email password and must be
stored as a GitHub secret.

No GitHub variable is required.

## Step 4: Deployment handoff

After both secret names appear in the repository's Actions secrets list, report
only that the Hugging Face secrets are saved. Do not provide either value.

The final deployment trigger will then:

1. validate the strict workers and sanitizer;
2. derive the Hugging Face username from `HF_TOKEN`;
3. create the public Docker Space and private state dataset;
4. install the Space secrets and configuration;
5. build and launch the service;
6. check `/health` and `/ready`;
7. start or observe a real hosted storefront scan;
8. require a successful scan, consistent catalog, and zero degraded active
   sources;
9. record the verified application URL and deployment receipt in GitHub.

## Hosted behavior

- Opening the app wakes a sleeping free Space.
- The catalog is immediately available from the last private snapshot.
- A stale catalog is refreshed after startup.
- A scheduled refresh runs every three hours while the Space is awake.
- Failed storefronts are quarantined instead of being represented as healthy.
- Catalog, status, quarantine, rejection, and scan state are backed up to the
  private dataset repository every 30 minutes when changed.
- The **Scan now** button asks for the operator token and keeps it only in that
  browser session.
