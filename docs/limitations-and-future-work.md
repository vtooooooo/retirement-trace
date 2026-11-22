# Limitations and future work

- The application uses server-configured demo accounts and synthetic-only data. Enterprise SSO, access provisioning UI, retention and redaction policies, and tamper-evident external audit are outside the verified scope.
- An anchored canonical participant table identifies synthetic records. Identity decisions are case-level and do not implement a global entity merge or golden-record service.
- The evidence graph is a case-centered projection with source lineage and link details. It does not implement deep multi-hop graph traversal or graph-wide search.
- Recommendation outcomes depend on a seeded simulator that favors rule-relevant evidence. Learned effort and reliability, prospective trials, and real-world outcomes are unvalidated.
- The seed loader generates structured source data directly. Vendor-format ingestion, generalized normalization, and schema-per-kind storage remain future work.
- Discrepancy detection covers intentionally generated scenarios. Real false positives, policy variance, malformed external inputs, and transport integrations are untested.
- The API reads portfolio projections in memory at demo scale. Large deployments would need query-level paging and performance validation. Demo operators provision accounts through server-side configuration.
- Benefits case resolution records an administrative decision with rationale. Separate real entitlement verification, payment authorization, disbursement, and completion workflows are deliberately unavailable.
