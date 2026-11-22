# Hosted V1.0 deployment

PensionTrace uses Cloudflare Pages for the React frontend and its same-origin API proxy. Render hosts FastAPI and managed PostgreSQL. The production build has no embedded dataset or account credentials. Use the cloud development environment and the hosting dashboards for every step.

## 1. Create the Pages project

1. In Cloudflare **Workers & Pages**, create a Pages project for **Direct Upload**. Set its production branch to `main`. GitHub Actions uploads both the built UI and the Pages Function using Wrangler. A dashboard ZIP upload is unnecessary.
2. Record the exact HTTPS Pages origin, such as `https://pensiontrace-example.pages.dev`. If using a custom domain, add it under **Custom domains** and wait for TLS to activate. Use one canonical origin for GitHub's public tests.
3. Create a Cloudflare API token scoped to the account with **Cloudflare Pages: Edit**. Record the Cloudflare account ID.

## 2. Configure the Render blueprint and accounts

1. In Render **Blueprints**, connect this repository and select `feature/pensiontrace` for the initial release. The [blueprint](../render.yaml) creates a Python web service and a managed PostgreSQL database in the same region. The service receives the internal database URL automatically. External database IP access is disabled. Application startup runs the versioned migrations and seeds missing synthetic tenants in a transaction. Existing cases are preserved.
2. Set `PT_FRONTEND_ORIGINS` to the exact Pages HTTPS origin. Multiple explicitly approved HTTPS origins can be comma-separated. Omit trailing slashes.
3. Generate at least 32 random bytes for `PT_EDGE_SECRET`, for example with `openssl rand -hex 32` in a private cloud terminal. Put the resulting value in a Render secret and in a Cloudflare Pages **Production** secret with the same name. The Pages Function authenticates to Render with this secret before the API will accept application requests.
4. Choose distinct usernames and strong unique passwords for the four demo operators. Run `python -m pensiontrace.hosting hash-password` once per password in the project’s Python environment. It prompts without echoing the passwords. Save the JSON array below as the Render secret `PT_DEMO_ACCOUNTS`, replacing each placeholder with the actual generated hash. Keep plaintext passwords in your password manager.

```json
[
  {"username":"demo-analyst","role":"analyst","password_hash":"<generated-hash>"},
  {"username":"demo-reviewer","role":"senior","password_hash":"<generated-hash>"},
  {"username":"demo-benefits","role":"benefits","password_hash":"<generated-hash>"},
  {"username":"demo-auditor","role":"auditor","password_hash":"<generated-hash>"}
]
```

The demo accounts share one persistent synthetic tenant. Distribute each credential privately to its assigned operator. Changing or deleting an account's password hash, role, or tenant invalidates its current sessions. Do not repurpose an existing username for a different person.

5. Record the Render HTTPS origin such as `https://pensiontrace-api-example.onrender.com`. Add it as Cloudflare Pages **Production** variable `API_ORIGIN`, without a trailing slash. In Render service settings, copy the service-specific **Deploy Hook** URL. Treat that entire URL as a secret.

## 3. Configure GitHub and publish

Create a GitHub Actions environment named `production`. Allow deployments from `feature/pensiontrace` for this release, and use an environment reviewer if desired. Set these GitHub Actions values:

| Scope | Name | Value |
| --- | --- | --- |
| Repository variable | `CLOUDFLARE_PAGES_PROJECT` | Exact Pages project name |
| Repository variable, optional | `PT_ENABLE_FEATURE_DEPLOY` | Set to `1` to allow deployments on pushes to `feature/pensiontrace` |
| Production variable | `PT_E2E_FRONTEND_URL` | Canonical HTTPS Pages origin |
| Production variable | `PT_E2E_API_URL` | HTTPS Render origin |
| Production secret | `RENDER_DEPLOY_HOOK` | Render service's deploy hook |
| Production secrets | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Cloudflare values |
| Production secrets | `PT_E2E_<ROLE>_USER` and `PT_E2E_<ROLE>_PASSWORD` | One pair each for `ANALYST`, `SENIOR`, `BENEFITS`, and `AUDITOR` |

To deploy before any merge, enable `PT_ENABLE_FEATURE_DEPLOY=1` and run the feature branch push workflow at the latest commit. You can also run a one-time Pages deploy from the existing Codex cloud terminal using Wrangler after setting the secured Cloudflare credential variables there. This uses no local laptop tooling. In the same cloud environment, verify the test and production build first, use the Render dashboard to deploy the latest commit on `feature/pensiontrace`, and confirm that `GET /ready` on Render returns the expected `X-PensionTrace-Revision`. Then run:

```sh
cd web
npm ci
VITE_API_BASE=/api/v1 npm run build
npx --yes wrangler@4.166.0 pages deploy dist --project-name="$CLOUDFLARE_PAGES_PROJECT" --branch=main
```

Set the public test origins and role credentials in your cloud environment's secret settings, then run `npm --prefix web test -- --grep-invert "backend process restart"` from the project root, with Chromium installed in that cloud environment. The E2E suite checks Pages-to-Render readiness, browser sign-in for all four roles, same-origin secure session cookies, participant search, audit export, and auditor restrictions. It defaults to read-only checks against public hosting.

For public write verification, create four additional server-side accounts with distinct usernames and `"tenant":"qa"`. Set the E2E secrets to those accounts and `PT_E2E_QA_WRITE=1`. The test refuses public writes in the ordinary `demo` tenant. The verification tenant is initialized on the next Render rollout. Its case and audit records persist independently.

After you approve a merge, switch the Render service branch to `main`. Update `render.yaml` accordingly. The GitHub workflow builds and tests changes on pull requests and pushes. On a deployment run, it triggers Render, waits for the expected revision and database readiness, deploys Pages, then runs browser checks against both public URLs. Keep the Render branch aligned with the revision being deployed. A successful asset upload alone does not establish a working site.

## Development and persistence checks

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm --prefix web ci
cd web && npx playwright install chromium && cd ..
scripts/verify-browser.sh
```

The verification script generates temporary credentials, tests the four-role workflow, restarts FastAPI, and reuses a browser session to verify the saved case and audit history. It uses an isolated SQLite database by default. To test with PostgreSQL, point `PT_BROWSER_DATABASE_URL` to an empty disposable database. For interactive development, configure your own `PT_DEMO_ACCOUNTS`, run `python -m pensiontrace.hosting initialize`, start Uvicorn on port 8000, and run `npm --prefix web run dev`. Vite proxies same-origin API requests. `PT_FRONTEND_ORIGINS` defaults to the loopback Vite origins in development.

## Cost and storage

The blueprint selects Render's paid **Starter** web service and **Basic-256mb** managed PostgreSQL. Check the monthly total, storage and backup terms shown by Render before creating resources. Cloudflare Pages has free-tier quotas, and Pages Function requests count toward applicable Workers limits. Render free web services can spin down and have slower first responses. Free PostgreSQL instances expire, and the web service filesystem is ephemeral. Use a persistent managed database for cases and sessions. Review backup and restore guarantees for the selected database plan and test a restore before relying on the dataset. [Render pricing](https://render.com/pricing) · [Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
