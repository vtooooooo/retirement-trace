# Synthetic data methodology

The default generator uses seed 73 and 6,600 participant anchors. It creates six source systems and emits deterministic pseudonyms, synthetic IDs, district labels, and integer-cent amounts. No original participant records or SSNs are imported. Each record has stable source ID, system, batch, ingestion date, version, and validation fields.

Variants include aliases, adjacent transpositions, omitted identifiers or employment years, different historical districts, conflicting identifiers, returned mail, payment anomalies, missing beneficiary documentation, and conflicting employment entries. Identifier flags use a source-claimed case linkage deliberately provided for those examples.

The generator emits separate identity-pair and issue labels. Labels live in memory during fitting and evaluation and are absent from evidence and public data. Unresolved identity rows have no verified participant anchor. Evaluation splits entire geographic blocks so neither participants nor comparison pairs span fit, calibration, and test.

The simulation has a fixed observation date of October 1, 2026. Defects are injected on a schedule and mirror known rules, so detection metrics only establish coverage of this fixture.
