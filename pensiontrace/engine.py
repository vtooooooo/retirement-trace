"""Deterministic synthetic ingestion and independently labeled evaluation."""

import math
import random
from collections import defaultdict
from itertools import combinations
from typing import Any

VERSION = "2026.1"
AS_OF = "2026-10-01"
ALIASES = {"bob": "robert", "liz": "elizabeth", "bill": "william"}
KINDS = {
    "uncashed": ("Uncashed benefit check", "high", "Inspect payment status"),
    "returned": ("Returned payment", "high", "Inspect payment status"),
    "duplicate": ("Possible duplicate payment", "high", "Compare payment references"),
    "identifier": ("Conflicting identifiers", "high", "Review historical identifiers"),
    "beneficiary": ("Missing beneficiary documentation", "medium", "Request internal beneficiary review"),
    "unpaid": ("Obligation without payment record", "high", "Reconcile obligation with payment ledger"),
    "service": ("Conflicting service history", "medium", "Compare employment periods"),
    "documentation": ("Incomplete case documentation", "medium", "Request authorized document review"),
}
SYSTEMS = (
    "HR Archive",
    "Pension Ledger",
    "Payroll Registry",
    "Payment Ledger",
    "Benefits Registry",
    "Mail Registry",
)


def generate(seed=73, count=6600):
    rng = random.Random(seed)
    people, truth, expected = [], {}, {}
    evidence: list[dict[str, Any]] = []

    def add(person, kind, system, **fields):
        uid = f"{kind[:3].upper()}-{len(evidence) + 1:06d}"
        evidence.append(
            dict(
                id=uid,
                person=person,
                kind=kind,
                system=system,
                batch=f"SYN-{seed}",
                ingested=AS_OF,
                version=1,
                validation="validated",
                **fields,
            )
        )
        return uid

    for i in range(count):
        person = f"PT-{i + 10001}"
        first = rng.choice(["Robert", "Elizabeth", "William", "Amelia", "Jordan", "Avery", "Maya", "Eleanor"])
        last = rng.choice(
            ["Miller", "Bennett", "Rivera", "Chen", "Morgan", "Parker", "Brooks", "Patel", "Hayes", "Reed"]
        )
        district = f"District {rng.randrange(1, 95):02}"
        year = rng.randrange(1974, 2014)
        name = f"{first} {last}"
        people.append(dict(id=person, name=name))
        region = f"Zone {i // 36 + 1:03}"
        employee = f"EMP-{i + 10482}"
        base = add(
            person,
            "identity",
            SYSTEMS[0],
            label=name,
            region=region,
            address=district,
            year=year,
            identifier=employee,
        )
        truth[base] = person
        issue = list(KINDS)[(i // 13) % len(KINDS)] if i % 13 == 0 else None
        if i % 2 == 0 or issue == "identifier":
            variant = {"Robert": "Bob", "Elizabeth": "Liz", "William": "Bill"}.get(first or "", first or "")
            if rng.random() < 0.07:
                variant = variant[:-2] + variant[-1] + variant[-2]
            linked = add(
                None,
                "identity",
                SYSTEMS[1],
                label=f"{variant} {last}",
                region=region,
                claimed_case_ref=person if issue == "identifier" else None,
                address=district if rng.random() > 0.29 else f"District {rng.randrange(1, 95):02}",
                year=year if rng.random() > 0.30 else None,
                identifier=f"LEG-{i + 4000}"
                if issue == "identifier"
                else employee
                if rng.random() > 0.34
                else None,
            )
            truth[linked] = person
        add(person, "address", SYSTEMS[0], label=district, status="historical")
        add(person, "employment", SYSTEMS[2], label=f"Service began {year}", year=year)
        if issue == "service":
            add(person, "employment", SYSTEMS[0], label=f"Service began {year + 4}", year=year + 4)
        cents = rng.randrange(100_000, 2_800_000)
        obligation = add(
            person, "obligation", SYSTEMS[1], label="Deferred benefit record", cents=cents, status="potential"
        )
        if issue != "unpaid":
            payment_status = {"uncashed": "issued", "returned": "returned"}.get(issue or "", "settled")
            add(
                person,
                "payment",
                SYSTEMS[3],
                label=f"Check {i + 5000}",
                reference=f"CHK-{i + 5000}",
                cents=cents,
                age=120 if issue == "uncashed" else 40,
                status=payment_status,
                obligation=obligation,
            )
            if issue == "duplicate":
                add(
                    person,
                    "payment",
                    SYSTEMS[3],
                    label=f"Check {i + 5000} • duplicate entry",
                    reference=f"CHK-{i + 5000}",
                    cents=cents,
                    age=40,
                    status="settled",
                    obligation=obligation,
                )
        if i % 7 == 0 or issue == "beneficiary":
            add(
                person,
                "beneficiary",
                SYSTEMS[4],
                label="Synthetic designation",
                status="missing documentation" if issue == "beneficiary" else "documented",
            )
        add(
            person,
            "correspondence",
            SYSTEMS[5],
            label="Annual statement",
            status="returned" if i % 11 == 0 else "delivered",
        )
        if issue != "documentation":
            add(person, "document", SYSTEMS[4], label="Benefit review packet", status="on file")
        if issue:
            expected[person] = issue
    return people, evidence, truth, expected


def features(a, b):
    def name(row):
        first, last = row["label"].lower().split()
        return ALIASES.get(first, first), last

    ia, ib = a.get("identifier"), b.get("identifier")
    ya, yb = a.get("year"), b.get("year")
    return [
        int(name(a) == name(b)),
        int(name(a)[1] == name(b)[1]),
        int(a["address"] == b["address"]),
        int(ya is not None and ya == yb),
        int(bool(ia and ia == ib)),
        int(bool(ia and ib and ia != ib)),
        int(ya is not None and yb is not None and ya != yb),
    ]


FEATURES = [
    "Normalized name",
    "Surname",
    "Address",
    "Employment year",
    "Identifier agreement",
    "Identifier conflict",
    "Employment year conflict",
]


def candidates(records):
    blocks = defaultdict(list)
    for row in records:
        if row["kind"] == "identity":
            blocks[(row["region"], row["label"].split()[-1])].append(row)
    for block in blocks.values():
        for a, b in combinations(block, 2):
            if a["system"] != b["system"]:
                left, right = (a, b) if a["person"] is not None else (b, a)
                yield left, right, features(left, right)


def probability(weights, vector):
    score = weights[0] + sum(w * x for w, x in zip(weights[1:], vector))
    return 1 / (1 + math.exp(-score))


def classify(p, vector):
    if vector[5] or 0.25 <= p < 0.90:
        return "abstain"
    return "proposed" if p >= 0.90 else "unlikely"


def evaluate(records, truth):
    splits: list[list[tuple[list[int], int]]] = [[], [], []]
    operational = []
    for a, b, vector in candidates(records):
        ta, tb = truth[a["id"]], truth[b["id"]]
        bucket_a, bucket_b = [((int(x[3:]) - 10001) // 36) % 5 for x in (ta, tb)]
        assert bucket_a == bucket_b
        split = 0 if bucket_a < 3 else bucket_a - 2
        splits[split].append((vector, int(ta == tb)))
        operational.append((a, b, vector))
    weights = [0.0] * 8
    train, calibration, test = splits
    if train:
        for _ in range(105):
            grad = [0.0] * 8
            for vector, label in train:
                error = probability(weights, vector) - label
                for j, value in enumerate([1, *vector]):
                    grad[j] += error * value
            weights = [w - 0.8 * (g / len(train) + 0.002 * w) for w, g in zip(weights, grad)]
    base = [-4, 2.7, 0.4, 1.8, 2.2, 5.4, -6, -3]
    # Fit a single calibration intercept to held-out blocks.
    shift = 0.0
    if calibration:
        for _ in range(40):
            adjusted = [weights[0] + shift, *weights[1:]]
            shift -= sum(probability(adjusted, x) - y for x, y in calibration) / len(calibration)
    weights[0] += shift

    def benchmark(method, threshold=0.90):
        scores = [(method(x), x, y) for x, y in test]
        tp = fp = tn = fn = abstain = 0
        for p, x, y in scores:
            accepted = p >= threshold and not x[5]
            tp += accepted and y
            fp += accepted and not y
            tn += not accepted and not y
            fn += not accepted and y
            abstain += classify(p, x) == "abstain"

        def ratio(a, b):
            return round(a / b, 5) if b else 0

        return dict(
            precision=ratio(tp, tp + fp),
            recall=ratio(tp, tp + fn),
            f1=ratio(2 * tp, 2 * tp + fp + fn),
            false_positive_rate=ratio(fp, fp + tn),
            false_negative_rate=ratio(fn, tp + fn),
            brier=ratio(sum((p - y) ** 2 for p, _, y in scores), len(scores)),
            abstention=ratio(abstain, len(scores)),
            tp=tp,
            fp=fp,
            tn=tn,
            fn=fn,
        )

    def model(x):
        return probability(weights, x)

    found = []
    for a, b, x in operational:
        score = model(x)
        disposition = classify(score, x)
        if disposition != "unlikely" or x[5]:
            found.append(
                dict(
                    id=f"ID-{a['id']}-{b['id']}",
                    left=a["id"],
                    right=b["id"],
                    person=a["person"],
                    score=round(score, 5),
                    status=disposition,
                    version=VERSION,
                    agreements=[FEATURES[j] for j in range(5) if x[j]],
                    conflicts=[FEATURES[j] for j in (5, 6) if x[j]],
                )
            )
    return found, dict(
        version=VERSION,
        split_counts=[len(s) for s in splits],
        identity={
            "Exact-rule baseline": benchmark(lambda x: float(x[4] and not x[5])),
            "Weighted baseline": benchmark(lambda x: probability(base, x)),
            "Calibrated logistic": benchmark(model),
        },
        curve=[dict(threshold=t, **benchmark(model, t)) for t in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.97)],
    )


def detect(records):
    groups = defaultdict(list)
    for row in records:
        groups[row.get("claimed_case_ref") or row["person"]].append(row)
    alerts = []
    for person, rows in groups.items():
        if person is None:
            continue
        by_kind = defaultdict(list)
        for row in rows:
            by_kind[row["kind"]].append(row)
        payments, identities, jobs = (by_kind[k] for k in ("payment", "identity", "employment"))
        checks = {
            "uncashed": [r for r in payments if r["status"] == "issued" and r["age"] >= 90],
            "returned": [r for r in payments if r["status"] == "returned"],
            "duplicate": [r for r in payments if sum(s["reference"] == r["reference"] for s in payments) > 1],
            "identifier": identities
            if len({r["identifier"] for r in identities if r["identifier"]}) > 1
            else [],
            "beneficiary": [r for r in by_kind["beneficiary"] if r["status"] == "missing documentation"],
            "unpaid": by_kind["obligation"] if not payments else [],
            "service": jobs if len({r["year"] for r in jobs}) > 1 else [],
            "documentation": by_kind["obligation"] if not by_kind["document"] else [],
        }
        for kind, matches in checks.items():
            if not matches:
                continue
            title, severity, action = KINDS[kind]
            contradictions = matches[1:] if kind in {"identifier", "service"} else []
            alerts.append(
                dict(
                    id=f"AL-{person[3:]}-{kind.upper()}",
                    person=person,
                    kind=kind,
                    title=title,
                    severity=severity,
                    source=matches[0]["system"],
                    detected=AS_OF,
                    version=VERSION,
                    supporting=[r["id"] for r in matches],
                    conflicting=[r["id"] for r in contradictions],
                    action=action,
                )
            )
    return alerts


def rank(alert, rows):
    lookup = {r["id"]: r for r in rows}
    supporting, conflicting = alert["supporting"], alert["conflicting"]
    choices = [
        (alert["action"], supporting, 0.78, 32, 0.13, "Analyst review"),
        (
            "Compare prior correspondence",
            [r["id"] for r in rows if r["kind"] == "correspondence"],
            0.55,
            18,
            0.20,
            "Analyst review",
        ),
        ("Refer to senior reviewer", conflicting or supporting, 0.69, 53, 0.05, "Independent senior review"),
        (
            "Inspect source records",
            [r["id"] for r in rows if r["kind"] == "identity"],
            0.59,
            24,
            0.17,
            "Analyst review",
        ),
    ]
    actions = []
    for name, refs, reliability, effort, risk, approval in choices:
        if refs and all(ref in lookup for ref in refs):
            # Information of a binary symmetric evidence channel at a uniform prior.
            error = (1 - reliability) / 2
            gain = 1 + error * math.log2(error) + (1 - error) * math.log2(1 - error)
            impact = 1.2 if name == alert["action"] else 1
            score = gain * impact - effort / 300 - risk * 0.3
            actions.append(
                dict(
                    name=name,
                    evidence=refs,
                    gain=round(gain, 4),
                    effort=effort,
                    risk=risk,
                    reliability=reliability,
                    impact=impact,
                    approval=approval,
                    score=round(score, 4),
                    version=VERSION,
                    uncertainty="Assumes equal prior odds and a synthetic evidence channel.",
                )
            )
    return sorted(actions, key=lambda a: (-a["score"], a["name"]))


def evaluate_actions(alerts, grouped, seed=73):
    rng = random.Random(seed + 203)
    result = {
        k: dict(steps=0, effort=0, resolved=0, unsafe=0)
        for k in ("Evidence-aware", "Random eligible", "Fixed priority", "Lowest cost")
    }
    holdout = [a for a in alerts if (int(a["person"][3:]) - 10001) // 36 % 5 == 4]
    for alert in holdout:
        options = rank(alert, grouped[alert["person"]])
        outcomes = {
            a["name"]: rng.random() < (0.70 if a["name"] == alert["action"] else 0.26) for a in options
        }
        shuffled = rng.sample(options, len(options))
        orders = (
            options,
            shuffled,
            sorted(options, key=lambda a: (a["approval"], a["name"])),
            sorted(options, key=lambda a: a["effort"]),
        )
        for measure, order in zip(result.values(), orders):
            for step in order:
                measure["steps"] += 1
                measure["effort"] += step["effort"]
                if outcomes[step["name"]]:
                    measure["resolved"] += 1
                    break
    return dict(
        cases=len(holdout),
        policies={
            k: {
                "mean_steps": round(v["steps"] / max(1, len(holdout)), 3),
                "mean_effort_minutes": round(v["effort"] / max(1, len(holdout)), 3),
                "resolved": v["resolved"],
                "unsafe": v["unsafe"],
            }
            for k, v in result.items()
        },
        assumptions="Shared seeded outcomes favor rule-relevant evidence. No real-world validation.",
    )
