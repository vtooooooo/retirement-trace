# API reference

FastAPI exposes interactive documentation at `/docs` and OpenAPI at `/openapi.json`. Protected endpoints use a server-side session cookie. In hosted mode, call them through the same-origin Pages Function. It provides its own edge credential to Render.

| Method and path | Result |
| --- | --- |
| GET /health/live | Process liveness |
| GET /ready | Database connectivity, migration version, and seed readiness |
| POST /api/v1/session | Sign in with a demo username and password |
| DELETE /api/v1/session | Revoke the current session and clear the cookie |
| GET /api/v1/session | Current tenant, operator role, and display name |
| GET /api/v1/workspace | Synthetic portfolio, case projections, evidence, and benchmarks |
| GET /api/v1/participants | Participant search by name or reference with offset and limit |
| GET /api/v1/cases | Case list with state, offset, and limit |
| GET /api/v1/cases/{id} | Alert, timeline, evidence, candidates, and next actions |
| GET /api/v1/cases/{id}/audit | Downloadable case and evidence JSON |
| POST /api/v1/cases/{id}/decisions | Transactional role-gated decision |

Decisions require JSON fields `action`, `note`, and `version`, an optional `reference`, and the `Idempotency-Key` header. Candidate approval requires a case-linked candidate. A credential failure returns 401, an unauthorized decision 403, a missing in-scope case 404, an invalid transition or stale version 409, and validation errors 422.
