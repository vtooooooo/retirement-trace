# Investigation decision engine

The action catalog contains internal evidence checks and independent review referrals. Steps are eligible when their required evidence IDs exist in the case projection. It models a binary question with equal prior odds and an evidence channel with error `e = (1 - reliability) / 2`. Expected information gain is `1 - H₂(e)` bits. The ranking score is:

```text
modeled information gain × impact − minutes / 300 − 0.30 × association risk
```

Rule-relevant checks use impact 1.2. Analyst estimates of reliability, minutes, and risk are synthetic constants. The UI shows ranked alternatives, supporting references, approval boundaries, and uncertainty. Operators can select an eligible alternative with recorded rationale.

For each held-out case, a seeded simulator shares sampled action outcomes across four policies. The simulator gives a higher success probability to the alert's rule-relevant action. It measures steps, modeled effort, and whether any eligible step resolved the simulation. Unsafe external actions are excluded by design. These comparisons do not estimate performance with real analyst workloads.
