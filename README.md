# PensionTrace AI

PensionTrace AI helps retirement operations teams reconcile fragmented synthetic records, surface potential benefit discrepancies, and document human review. A case carries rule evidence, identity candidates, ranked investigation actions, and an auditable decision history. Source claims, identity review, administrative case resolution, and payment ledger status are distinct.

The application includes eight workspaces covering operations, identity, discrepancies, evidence, recommendations, workflow, analytics, and governance. The public demo is a static read-only export of 32 cases with the portfolio's aggregate benchmarks. The authenticated synthetic environment also records role-gated decisions against persisted data.

## Build and run in the cloud workspace

Requires Python 3.12 and Node.js 24. No local installation is required to use a published demo.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pensiontrace migrate
python -m pensiontrace seed
python -m pensiontrace export
npm --prefix web ci
npm --prefix web run build
npm --prefix web run preview
```

The built site is in `web/dist/`. For authenticated development and the PostgreSQL profile, see the [deployment guide](docs/deployment-guide.md).

## Checks

```sh
ruff check pensiontrace tests
ruff format --check pensiontrace tests
mypy pensiontrace
python -m pytest -q
python -m pensiontrace evaluate
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web run test:unit
cd web
npx playwright install chromium
npm test
```

## Project documentation

- [Product scope and workspaces](docs/product-requirements.md)
- [Architecture](docs/system-architecture.md) and [data model](docs/data-model.md)
- [Synthetic data](docs/synthetic-data-methodology.md), [matching](docs/entity-resolution-methodology.md), [action ranking](docs/investigation-decision-engine.md), and [measured results](docs/model-evaluation.md)
- [Governance](docs/security-and-governance.md), [API](docs/api-reference.md), and [deployment](docs/deployment-guide.md)
- [Demo walkthrough and screenshots](docs/recruiter-demo-guide.md)
- [Limitations and future work](docs/limitations-and-future-work.md)
