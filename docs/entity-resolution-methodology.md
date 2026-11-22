# Entity-resolution methodology

Candidate generation compares different identity sources within a shared zone and surname. Inputs are normalized first and last name, surname, district, employment year, exact identifier, identifier conflict, and employment year conflict. Missing identifiers and employment years neither agree nor disagree. A short alias dictionary normalizes common variants with deterministic behavior.

The model is logistic regression with gradient descent and L2 regularization. A separate geographic-block cohort fits an intercept adjustment. Baselines use exact identifier rules and fixed weighted probabilities. An operational threshold of 0.90 caps candidate proposals and any explicit identifier conflict forces abstention. A score at least 0.25 and below 0.90 also abstains. Lower scoring non-conflicting pairs are omitted from comparison queues.

Scores estimate matching within generated candidate blocks. They are conditional on the block policy, and aliases, anchor data, transpositions, and shared districts are simplified. Human approvals are case-scoped and audited.
