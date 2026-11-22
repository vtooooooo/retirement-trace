# Measured model and workflow evaluation

Run the following against a fresh default-seed database.

```sh
python -m pensiontrace seed
python -m pensiontrace evaluate
```

Seed 73 produced 6,600 synthetic participant anchors, 9,964 identity source records, and 50,562 total source records. The set includes 6,663 employment records, 6,600 obligations, 6,601 payments, 997 beneficiary records, and 6,600 correspondence events. The rule suite identified all 508 injected cases with zero extra flags on this fixture.

The candidate-pair counts were 9,076 fit, 2,922 calibration, and 2,919 test. The held-out set included 661 positive and 2,258 negative pairs.

| Match method | Precision | Recall | F1 | False-positive rate | False-negative rate | Brier | Abstention |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact-rule baseline | 100.00% | 65.36% | 79.05% | 0.00% | 34.64% | 0.07845 | 53.55% |
| Weighted baseline | 100.00% | 82.45% | 90.38% | 0.00% | 17.55% | 0.01128 | 57.86% |
| Calibrated logistic | 100.00% | 75.49% | 86.03% | 0.00% | 24.51% | 0.01117 | 59.95% |

The weighted baseline accepted 46 more labeled true pairs than logistic at the selected threshold. At a 0.50 threshold, logistic precision fell to 99.37% with four false accepts, and recall rose to 94.86%. Common misses include true pairs with conflicting IDs and otherwise matching pairs whose missing evidence keeps them below the threshold. These are candidate-only results on simplified synthetic distributions. Zero observed false accepts at the 0.90 threshold gives no guarantee in production. Brier score measures probability error across all held-out pairs, before applying the operational abstention gate.

## Investigation simulation

All policies evaluated the same 100 cases and shared case-specific sampled outcomes.

| Policy | Mean steps | Mean effort, modeled minutes | Resolved | Unsafe actions |
| --- | ---: | ---: | ---: | ---: |
| Evidence-aware | 1.45 | 48.99 | 96 | 0 |
| Fixed priority | 2.06 | 53.12 | 96 | 0 |
| Lowest cost | 2.32 | 56.58 | 96 | 0 |
| Random eligible | 2.14 | 67.21 | 96 | 0 |

The score rewards rule-relevant evidence, and the simulator assumes that same evidence is likelier to succeed. Unsafe actions are outside the action catalog. The simulation measures search ordering under those assumptions. It does not model erroneous final determinations or real-world resolution accuracy.
