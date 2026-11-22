import json

import pytest
from fastapi.testclient import TestClient

from pensiontrace.api import app
from pensiontrace.db import Store, pack
from pensiontrace.engine import candidates, classify, detect, evaluate, features, generate, rank


@pytest.fixture(scope="module")
def source():
    return generate(count=510)


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    return prepare_db(monkeypatch)


def prepare_db(monkeypatch):
    for role in ("analyst", "senior", "benefits", "auditor", "admin"):
        monkeypatch.setenv(f"PT_{role.upper()}_TOKEN", f"synthetic-test-{role}")
    store = Store()
    assert store.seed(count=510)
    return store


def auth(role):
    return {"Authorization": f"Bearer synthetic-test-{role}"}


def test_seed_reproducible_and_labels_separate(source):
    people, evidence, truth, _ = source
    assert generate(count=510) == source
    assert generate(seed=74, count=510) != source
    assert len(people) == len({p["id"] for p in people})
    assert all({"batch", "ingested", "system", "version", "validation"} <= r.keys() for r in evidence)
    alternate = [r for r in evidence if r["kind"] == "identity" and r["system"] == "Pension Ledger"]
    assert all(r["person"] is None and r["id"] in truth for r in alternate)


def test_leakage_resistant_blocks_and_evaluation(source):
    _, records, truth, _ = source
    groups = {}
    for left, right, vector in candidates(records):
        assert left["region"] == right["region"]
        assert features(left, right) == vector
        buckets = {(int(truth[r["id"]][3:]) - 10001) // 36 % 5 for r in (left, right)}
        assert len(buckets) == 1
        for r in (left, right):
            assert groups.setdefault(truth[r["id"]], next(iter(buckets))) in buckets
    matches, results = evaluate(records, truth)
    assert evaluate(records, truth) == (matches, results)
    assert all(results["split_counts"])
    assert len(results["identity"]) == 3
    assert len(results["curve"]) == 7
    assert all(0 <= row["brier"] <= 1 for row in results["identity"].values())
    assert all(0 <= m["score"] <= 1 for m in matches)
    assert not any(m["status"] == "proposed" and "Identifier conflict" in m["conflicts"] for m in matches)
    assert classify(0.999, [1, 1, 1, 1, 0, 1, 0]) == "abstain"
    assert classify(0.6, [1, 1, 0, 0, 0, 0, 0]) == "abstain"


def test_all_discrepancies_have_source_evidence_and_rank_actions(source):
    _, rows, _, expected = source
    alerts = detect(rows)
    assert {a["person"]: a["kind"] for a in alerts} == expected
    assert len({a["kind"] for a in alerts}) == 8
    lookup = {r["id"]: r for r in rows}
    for a in alerts:
        assert a["supporting"] and set(a["conflicting"]) <= lookup.keys()
        actions = rank(
            a, [*map(lookup.get, a["supporting"]), *[r for r in rows if r["person"] == a["person"]]]
        )
        assert actions == sorted(actions, key=lambda x: (-x["score"], x["name"]))
        assert all(act["approval"] and 0 <= act["gain"] <= 1 for act in actions)


def test_migration_foreign_keys_and_public_export(db):
    db.migrate()
    assert db.seed(count=510) is False
    with db.transaction() as conn:
        assert db.sql(conn, "SELECT COUNT(*) AS n FROM schema_versions").fetchone()["n"] == 1
        with pytest.raises(Exception, match="(?i)foreign key"):
            db.sql(conn, "INSERT INTO evidence VALUES (?,?,?,?,?)", "demo", "XX", "unknown", "identity", "{}")
        conn.rollback()
    data = db.snapshot("demo", 32, public=True)
    assert len(data["cases"]) == 32
    assert pack(data) == pack(db.snapshot("demo", 32, public=True))
    assert "ground_truth" not in pack(data)
    for case in data["cases"]:
        assert set(case["evidence"]) <= data["evidence"].keys()
        assert set(case["alert"]["supporting"]) <= set(case["evidence"])
        for match in data["matches"]:
            if match["person"] == case["person"]:
                assert {match["left"], match["right"]} <= data["evidence"].keys()


def test_api_permissions_validation_and_tenant_scope(db, monkeypatch):
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/cases").status_code == 401
    assert client.get("/api/v1/cases?limit=101", headers=auth("auditor")).status_code == 422
    people = client.get("/api/v1/participants?q=PT-10001", headers=auth("auditor")).json()
    assert len(people) == 1
    assert people[0]["id"] == "PT-10001"
    assert db.seed(count=28, tenant="other")
    monkeypatch.setenv("PT_AUDITOR_TENANT", "other")
    assert client.get("/api/v1/cases/RC-1049", headers=auth("auditor")).status_code == 404
    assert client.get("/api/v1/cases/RC-1049", headers=auth("analyst")).status_code == 200
    monkeypatch.setenv("PT_ADMIN_TOKEN", "synthetic-test-analyst")
    assert client.get("/api/v1/cases", headers=auth("analyst")).status_code == 401


def test_case_decisions_audit_and_idempotency(db):
    client = TestClient(app)
    payload = db.snapshot("demo")
    case = next(c for c in payload["cases"] if c["alert"]["kind"] == "identifier")
    match = next(
        m
        for m in payload["matches"]
        if m["person"] == case["person"] and m["right"] in case["alert"]["conflicting"]
    )

    def decide(role, action, version, key=None, reference=None):
        return client.post(
            f"/api/v1/cases/{case['id']}/decisions",
            headers={**auth(role), "Idempotency-Key": key or f"test-{role}-{action}"},
            json={
                "action": action,
                "version": version,
                "note": "Reviewed synthetic records",
                "reference": reference,
            },
        )

    version = 1
    if case["state"] == "Detected":
        assert decide("analyst", "triage", version).status_code == 200
        version += 1
    if case["state"] == "Triaged":
        assert decide("analyst", "investigate", version).status_code == 200
        version += 1
    first = decide("analyst", "request_review", version)
    assert first.status_code == 200
    assert decide("analyst", "request_review", version).json() == first.json()
    assert decide("senior", "approve_identity", version, reference=match["id"]).status_code == 409
    version += 1
    assert decide("analyst", "approve_identity", version, reference=match["id"]).status_code == 403
    assert decide("auditor", "resolve", version).status_code == 403
    assert decide("senior", "approve_review", version).status_code == 422
    assert decide("senior", "approve_identity", version, reference="unrelated").status_code == 422
    assert decide("senior", "approve_identity", version, reference=match["id"]).status_code == 200
    assert decide("benefits", "resolve", version + 1).json()["state"] == "Resolved"
    assert decide("analyst", "note", version + 2).status_code == 409
    assert decide("analyst", "reopen", version + 2).json()["state"] == "Reopened"
    report = client.get(f"/api/v1/cases/{case['id']}/audit", headers=auth("auditor"))
    assert report.status_code == 200
    events = json.loads(report.text)["case"]["timeline"]
    assert events[-1]["kind"] == "reopen"
    assert any(e["kind"] == "approve_identity" and e["reference"] == match["id"] for e in events)
    with pytest.raises(ValueError, match="pristine"):
        db.snapshot("demo", 32, public=True)


def test_postgresql_migration_and_workflow(monkeypatch):
    import os

    url = os.environ.get("PT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set PT_TEST_POSTGRES_URL to a clean PostgreSQL test database")
    monkeypatch.setenv("DATABASE_URL", url)
    store = prepare_db(monkeypatch)
    assert store.pg
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/v1/cases/RC-1042/decisions",
        headers={**auth("analyst"), "Idempotency-Key": "pg-triage-1"},
        json={"action": "triage", "note": "Reviewed synthetic data", "version": 1},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "Triaged"
