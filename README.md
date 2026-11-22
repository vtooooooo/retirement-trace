# PensionTrace AI V1.0

PensionTrace AI helps retirement operations teams reconcile fragmented synthetic records, flag potential benefit discrepancies, and document human review. A case carries rule evidence, identity candidates, ranked investigation actions, and a persistent audit history. Source claims, identity decisions, administrative resolution, and payment ledger status are distinct.

The app includes eight workspaces for operations, identity, discrepancies, evidence, recommendations, workflow, analytics, and governance. The hosted build uses authenticated FastAPI data through Cloudflare Pages. Neon Free PostgreSQL stores cases and sessions while Render Free runs FastAPI. The app supports synthetic data only.

## Build and verify in the cloud workspace

Requires Python 3.12 and Node.js 24. No laptop installation is required.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
ruff check pensiontrace tests
ruff format --check pensiontrace tests
mypy pensiontrace
python -m pytest -q
npm --prefix web run lint
npm --prefix web run test:unit
cd web && npx playwright install chromium && cd ..
scripts/verify-browser.sh
```

The frontend build is in `web/dist/`. The browser harness exercises live local APIs and verifies persistence after a process restart. Configure `PT_TEST_POSTGRES_URL` and `PT_BROWSER_DATABASE_URL` with separate empty PostgreSQL databases to test both suites on PostgreSQL.

## Project documentation

- [Cloudflare Pages, Render Free, and Neon Free deployment](docs/deployment-guide.md)
- [Product scope](docs/product-requirements.md), [architecture](docs/system-architecture.md), and [data model](docs/data-model.md)
- [Synthetic data](docs/synthetic-data-methodology.md), [matching](docs/entity-resolution-methodology.md), [action ranking](docs/investigation-decision-engine.md), and [measured results](docs/model-evaluation.md)
- [Governance](docs/security-and-governance.md), [API](docs/api-reference.md), and [demo walkthrough](docs/recruiter-demo-guide.md)
- [Limitations and future work](docs/limitations-and-future-work.md)
