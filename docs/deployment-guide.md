# Deployment and development

## Cloudflare Pages

1. In Cloudflare, open **Workers & Pages**, create a **Pages** project using **Direct Upload**, and select `main` as the production branch if prompted. Record the project name and account ID.
2. Create an API token scoped to the Cloudflare account with **Cloudflare Pages: Edit**. Add it as the GitHub Actions secret `CLOUDFLARE_API_TOKEN`. Add the account ID as `CLOUDFLARE_ACCOUNT_ID`.
3. Add a GitHub Actions repository variable `CLOUDFLARE_PAGES_PROJECT` containing the exact project name. Enable GitHub Actions for the repository.
4. Merge through the normal approval process, or dispatch **Verify and publish static demo** against `main` after the workflow is there. The workflow builds and validates the artifact on GitHub-hosted Linux, uploads `pensiontrace-pages`, and deploys that artifact with Wrangler.
5. Verify the Pages URL from the deployment job. Check the first page, a deep-link workspace, evidence source navigation, and audit download. Cloudflare only serves the static output and requires no backend runtime.

Pull requests run the same validation without publishing. The deploy job requires the project variable and a `main` run. Do not enter deployment secrets into the source tree or chat.

## Engineer profile

Activate the Python environment from the README. Configure a PostgreSQL database owned by a dedicated development user and set `DATABASE_URL` from environment settings or a shell credential store, or leave it unset for SQLite. Do not point the seed command at a production database.

```sh
python -m pensiontrace migrate
python -m pensiontrace seed
python -m pensiontrace export
python -m uvicorn pensiontrace.api:app --host 127.0.0.1 --port 8000
```

Set distinct local credentials before launching the API using `PT_ANALYST_TOKEN`, `PT_SENIOR_TOKEN`, `PT_BENEFITS_TOKEN`, `PT_AUDITOR_TOKEN`, and `PT_ADMIN_TOKEN`. An individual role can be disabled by omitting its credential. Set the corresponding `PT_<ROLE>_TENANT` to bind a role to a different configured tenant; the default is `demo`. In another terminal run `npm --prefix web run dev`. Use **Connect local API** from the profile menu and enter a scoped credential. For the PostgreSQL smoke test, supply `PT_TEST_POSTGRES_URL` pointing to an empty disposable database.

The live browser suite requires a fresh synthetic database and the test-only analyst and senior credentials specified in the CI job. The database used for static export must have no case changes.
