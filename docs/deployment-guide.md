# Deploy V1.0 on the three free plans

Use **Neon Free PostgreSQL**, **Render Free Web Service**, and **Cloudflare Pages Free**. The commands below run in the Codex cloud terminal inside your browser. Keep all secrets out of chat, Git, and the browser bundle.

## 1. Create Neon Free PostgreSQL

1. Sign in to [Neon Console](https://console.neon.tech/). Create a project named `pensiontrace` on the **Free** plan. Choose a region near the Render service, preferably US West (Oregon) if available. Keep the default database and branch, such as `neondb` and `production`.
2. In the project dashboard, click **Connect**. Choose the production database and a role that can create tables and indexes in it. Turn **Connection pooling** on and copy the PostgreSQL URL. It should have an HTTPS-trusted `*.neon.tech` hostname, typically with `-pooler` in the host, and should include the database name and the TLS options Neon provides. The scheme is `postgresql://`. Store the URL in your password manager.
3. Leave Neon scale-to-zero enabled. There is no database service to create in Render. Keep the Neon project and branch in place across Render redeployments.

In hosted mode, psycopg requires TLS certificate and hostname verification with the system CA store and requires SCRAM channel binding. The initial schema and seed use transaction-scoped locks and bulk copies, which are compatible with transaction pooling. Automatic prepared statements are disabled on hosted connections.

## 2. Create a Cloudflare Pages Free project

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), open **Workers & Pages → Create application → Pages → Connect to Git**. Authorize the GitHub repository `vtooooooo/retirement-trace`.
2. Set a project name and choose `feature/pensiontrace` as the **Production branch**. Use framework preset **None**, **Root directory** `web`, **Build command** `npm run build`, and **Build output directory** `dist`. Add build variable `NODE_VERSION=24`. Select **Save and Deploy**. The frontend can build before the API exists.
3. Copy the canonical HTTPS Pages origin, such as `https://pensiontrace-example.pages.dev`. Then open the Pages project’s **Settings → Variables and Secrets**. After creating Render in the next section, add these to **Production**:

   | Name | Type | Value |
   | --- | --- | --- |
   | `API_ORIGIN` | Text | The exact Render HTTPS origin, without a trailing slash |
   | `PT_EDGE_SECRET` | Secret | The same random value stored on Render |

The Pages Function is under `web/functions`. The frontend uses `/api/v1` on its own origin, so users never receive the edge secret. If an existing project uses **Direct Upload**, keep it and use the optional GitHub Actions deployment below.

## 3. Create the Render Free Web Service

In the [Render dashboard](https://dashboard.render.com/), choose **New → Blueprint**, connect the repository and select `feature/pensiontrace`. Confirm the preview lists **one Free web service** and no database. If your dashboard does not offer a Free Blueprint service, choose **New → Web Service** instead and apply the settings from [render.yaml](../render.yaml). Use the **Free** instance type, Python runtime, repository root, Oregon region, the feature branch, and Auto Deploy **Off**. Copy the build command, start command, health check path, and Python version from the Blueprint.

In the service’s **Environment** tab, configure:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | The pooled PostgreSQL URL copied from Neon. Store it as a Render secret. |
| `PT_HOSTED` | `1` |
| `PT_FRONTEND_ORIGINS` | The exact Pages HTTPS origin, with no trailing slash |
| `PT_EDGE_SECRET` | A server-only random value. Generate it with `openssl rand -hex 32` in a private cloud terminal and save it on both hosts. |
| `PT_DEMO_ACCOUNTS` | JSON array of distinct accounts and password hashes for the four roles |

To generate each account hash in the browser’s cloud terminal, activate the project Python environment and run `python -m pensiontrace.hosting hash-password`. The prompt does not echo passwords. Save the plaintext passwords privately and put the hashes in Render:

```json
[
  {"username":"demo-analyst","role":"analyst","password_hash":"<generated-hash>"},
  {"username":"demo-reviewer","role":"senior","password_hash":"<generated-hash>"},
  {"username":"demo-benefits","role":"benefits","password_hash":"<generated-hash>"},
  {"username":"demo-auditor","role":"auditor","password_hash":"<generated-hash>"}
]
```

Choose **Save, rebuild, and deploy** or **Manual Deploy → Deploy latest commit**. Copy the service’s `https://…onrender.com` origin into Pages `API_ORIGIN`, set the Pages edge secret, and redeploy the Pages production deployment from its dashboard. The first API start initializes only missing tenants. Existing committed case and audit data in Neon survives restarts. If migrating data from a previously deployed database, restore a verified backup into Neon before pointing the service at it.

## 4. Verify the deployment and an idle restart

1. Open the Render `/ready` URL, then open the Pages `/api/ready` URL. Both must return `{"status":"ok"}`. Render’s routine platform health check uses `/health/live` so that it does not query Neon continuously.
2. Open the Pages URL in your browser. Sign in, search for a participant, record a synthetic case change as an analyst, and check it with the auditor account. Use separate senior and benefits accounts for approval and resolution. Compare audit history before and after refresh.
3. To verify natural idle behavior, keep the browser session, close active app tabs without signing out, and wait at least 16 minutes without application requests, health monitors, or deployment jobs. Open the Pages URL again and allow time for the backend to wake. Confirm you can still open the case and see the same audit entry. The optional Playwright scenario records the backend boot ID before and after the wait. If other traffic kept the service awake, it reports that the restart was not observed.

From the project root in the cloud terminal, set `PT_E2E_FRONTEND_URL` and `PT_E2E_API_URL` to the HTTPS origins and set `PT_E2E_<ROLE>_USER` and `PT_E2E_<ROLE>_PASSWORD` for `ANALYST`, `SENIOR`, `BENEFITS`, and `AUDITOR` in secure environment settings. Then run the public smoke suite:

```sh
npm --prefix web test -- --grep-invert "backend process restart"
PT_VERIFY_FREE_IDLE=1 npm --prefix web test -- --grep "hosted free service"
```

For a public test that writes workflow decisions automatically, create four additional server-side accounts with distinct usernames and `"tenant":"qa"`. Deploy Render to initialize the QA tenant, point the browser test credentials at those accounts, and set `PT_E2E_QA_WRITE=1`. Automated write tests refuse to modify the ordinary demo tenant.

## Optional GitHub Actions deployment

The repository workflow validates against disposable PostgreSQL and tests a real FastAPI process restart on CI. It can also deploy Render and a **Direct Upload** Pages project. For the browser dashboard Git integration above, leave the repository’s `CLOUDFLARE_PAGES_PROJECT` Actions variable unset and deploy Render from its dashboard. For Direct Upload, create the Pages project with production branch `main` using `npx wrangler@4.166.0 pages project create <name> --production-branch main` from a browser cloud terminal with Cloudflare authentication. GitHub Actions deploys the feature commit into the Pages production branch without merging the Git branch.

| Scope | Values |
| --- | --- |
| Repository Actions variables | `CLOUDFLARE_PAGES_PROJECT` and `PT_ENABLE_FEATURE_DEPLOY=1` to opt into feature-branch publication |
| GitHub `production` environment variables | `PT_E2E_FRONTEND_URL`, `PT_E2E_API_URL`, and optionally `PT_E2E_QA_WRITE` or `PT_VERIFY_FREE_IDLE` |
| GitHub `production` environment secrets | `CLOUDFLARE_API_TOKEN` (Pages Edit), `CLOUDFLARE_ACCOUNT_ID`, `RENDER_DEPLOY_HOOK` from Render service settings, and the four test account credential pairs |

Allow `feature/pensiontrace` to deploy to the `production` environment. The workflow waits for the expected commit’s Render readiness before publishing Pages and running public browser checks. Keep the optional 16-minute idle test off in CI when avoiding runner-minute usage. Run it in the cloud terminal instead.

## Free-tier limits

- Render Free offers 512 MB of RAM, spins down after about 15 minutes without inbound traffic, and shares a monthly free instance-hour quota across the workspace. Wake-up can take about a minute. Its filesystem is ephemeral. Render may suspend free services with unusually high outbound traffic, including traffic to external databases. [Render Free limits](https://render.com/docs/free)
- Neon Free uses scale-to-zero and has compute, storage, and transfer allowances. Check the **Usage** page in your Neon account. Reaching a quota can interrupt the app. The database persists through idle compute and Render redeployments, while project deletion or exhausted provider quotas can affect access. [Neon plans](https://neon.com/docs/introduction/plans)
- Pages Free has build and function request limits. The function forwards each API request, and the browser retries eligible reads once after a temporary failure. The app never automatically replays a case mutation. For a $0 budget, stay on all three free plans and keep any GitHub Actions paid overage disabled. [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)

A public deployment is verified only after both URLs and the authenticated workflows pass. The local PostgreSQL restart harness does not establish actual Render idle timing or Neon quota behavior.
