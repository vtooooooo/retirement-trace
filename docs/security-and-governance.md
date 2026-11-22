# Security and governance

The public artifact consists of static assets. It contains synthetic examples and aggregate benchmark results. The API is available only in the synthetic development profile. That profile uses distinct role bearer credentials from environment variables. Duplicate credentials are refused. Bearer credentials remain in browser memory. Tenant scope is bound server-side per role, and query parameters cannot choose it.

Analysts triage and investigate and may submit review requests. Senior reviewers adjudicate independently and can return a case for further work. Benefits operators resolve reviewed cases. Audit and system administrator profiles cannot change business records. Decisions require rationale, current revision, and an idempotency key. Events persist actor, timestamp, state, version, and action reference.

Attachments are internal reference metadata. There is no file upload, participant contact, disbursement, or external identity verification. Do not enter real participant information. This profile does not include production SSO, organization provisioning, evidence redaction, retention administration, or immutable external audit storage. Before a real deployment those features need implementation and assessment.
