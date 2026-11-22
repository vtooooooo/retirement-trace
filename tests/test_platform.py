import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pensiontrace.api import app
from pensiontrace.auth import ROLES, hash_password
from pensiontrace.db import Store, pack
from pensiontrace.engine import candidates, classify, detect, evaluate, features, generate, rank
from pensiontrace.hosting import initialize


@pytest.fixture(scope="module")
def source():
    return generate(count=510)


@pytest.fixture
def db(monkeypatch, tmp_path, demo_accounts):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    return prepare_db(monkeypatch, demo_accounts)


ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(scope="module")
def demo_accounts():
    return [
        {"username": role, "role": role, "password_hash": hash_password(demo_password(role))}
        for role in ROLES
    ]


def demo_password(role):
    return f"synthetic-test-purpose-{role}"


def prepare_db(monkeypatch, demo_accounts):
    monkeypatch.setenv("PT_DEMO_ACCOUNTS", json.dumps(demo_accounts))
    store = Store()
    assert store.seed(count=510)
    return store


def account_client(role):
    client = TestClient(app)
    response = client.post(
        "/api/v1/session",
        headers=ORIGIN,
        json={"username": role, "password": demo_password(role)},
    )
    assert response.status_code == 200
    return client


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
        assert db.sql(conn, "SELECT COUNT(*) AS n FROM schema_versions").fetchone()["n"] == 2
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


def test_initialized_database_skips_seed_and_migrations(db, monkeypatch):
    before = db.snapshot("demo", 1)

    def unexpected(*_args, **_kwargs):
        pytest.fail("Startup attempted to change an initialized database")

    monkeypatch.setattr(db, "migrate", unexpected)
    monkeypatch.setattr(db, "seed", unexpected)
    initialize(db, ["demo"])
    assert db.snapshot("demo", 1) == before


def test_api_permissions_validation_and_tenant_scope(db, monkeypatch, demo_accounts):
    client = TestClient(app)
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ok"}
    assert client.get("/api/v1/cases").status_code == 401
    analyst = account_client("analyst")
    assert analyst.get("/api/v1/cases?limit=101").status_code == 422
    people = analyst.get("/api/v1/participants?q=PT-10001").json()
    assert people == [{"id": "PT-10001", "name": people[0]["name"], "case_id": "RC-1042"}]
    assert db.seed(count=28, tenant="qa")
    moved = [{**a, "tenant": "qa"} if a["role"] == "auditor" else a for a in demo_accounts]
    monkeypatch.setenv("PT_DEMO_ACCOUNTS", json.dumps(moved))
    auditor = account_client("auditor")
    assert auditor.get("/api/v1/cases/RC-1049").status_code == 404
    assert analyst.get("/api/v1/cases/RC-1049").status_code == 200


def test_session_security_logout_rotation_and_throttling(db, monkeypatch, demo_accounts):
    monkeypatch.setattr("pensiontrace.auth.time", SimpleNamespace(time=lambda: 1_800_000_100))
    client = TestClient(app)
    path = "/api/v1/session"
    login = {"username": "analyst", "password": demo_password("analyst")}
    assert client.post(path, json=login).status_code == 403
    assert client.post(path, json=login, headers={"Origin": "https://other.test"}).status_code == 403
    response = client.post(path, json=login, headers=ORIGIN)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    cookie = client.cookies["pt_session"]
    restarted = TestClient(app, cookies={"pt_session": cookie})
    assert restarted.get(path).json()["role"] == "analyst"
    assert restarted.delete(path).status_code == 403
    assert restarted.delete(path, headers=ORIGIN).status_code == 204
    assert client.get(path).status_code == 401
    assert client.post(path, json=login, headers=ORIGIN).status_code == 200
    rotated = [
        {**a, "password_hash": hash_password("changed-synthetic-password")} if a["role"] == "analyst" else a
        for a in demo_accounts
    ]
    monkeypatch.setenv("PT_DEMO_ACCOUNTS", json.dumps(rotated))
    assert client.get(path).status_code == 401
    for _ in range(10):
        assert (
            client.post(
                path, json={"username": "unknown", "password": "incorrect"}, headers=ORIGIN
            ).status_code
            == 401
        )
    limited = client.post(path, json={"username": "unknown", "password": "incorrect"}, headers=ORIGIN)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_hosted_edge_and_secure_cookie_policy(db, monkeypatch):
    monkeypatch.setenv("PT_HOSTED", "1")
    monkeypatch.setenv("PT_EDGE_SECRET", "edge-only-fixture" * 3)
    monkeypatch.setenv("PT_FRONTEND_ORIGINS", "https://pension.example")
    client = TestClient(app, base_url="https://api.example")
    login = {"username": "analyst", "password": demo_password("analyst")}
    assert client.get("/api/v1/session").status_code == 403
    edge = {"X-PT-Edge-Secret": "edge-only-fixture" * 3}
    assert client.post("/api/v1/session", headers={**edge, **ORIGIN}, json=login).status_code == 403
    response = client.post(
        "/api/v1/session", headers={**edge, "Origin": "https://pension.example"}, json=login
    )
    assert response.status_code == 200
    assert "__Host-pt_session=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"] and "Path=/" in response.headers["set-cookie"]
    assert "Domain=" not in response.headers["set-cookie"]
    assert "strict-transport-security" in response.headers
    assert client.get("/api/v1/session", headers=edge).status_code == 200
    assert client.get("/ready").status_code == 503


def test_case_decisions_audit_and_idempotency(db):
    clients = {role: account_client(role) for role in ROLES}
    payload = db.snapshot("demo")
    case = next(c for c in payload["cases"] if c["alert"]["kind"] == "identifier")
    match = next(
        m
        for m in payload["matches"]
        if m["person"] == case["person"] and m["right"] in case["alert"]["conflicting"]
    )

    def decide(role, action, version, key=None, reference=None):
        return clients[role].post(
            f"/api/v1/cases/{case['id']}/decisions",
            headers={**ORIGIN, "Idempotency-Key": key or f"test-{role}-{action}"},
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
    report = clients["auditor"].get(f"/api/v1/cases/{case['id']}/audit")
    assert report.status_code == 200
    events = json.loads(report.text)["case"]["timeline"]
    assert events[-1]["kind"] == "reopen"
    assert any(e["kind"] == "approve_identity" and e["reference"] == match["id"] for e in events)
    with pytest.raises(ValueError, match="pristine"):
        db.snapshot("demo", 32, public=True)


def test_postgresql_migration_and_workflow(monkeypatch, demo_accounts):
    import os

    url = os.environ.get("PT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set PT_TEST_POSTGRES_URL to a clean PostgreSQL test database")
    monkeypatch.setenv("DATABASE_URL", url)
    store = prepare_db(monkeypatch, demo_accounts)
    assert store.pg
    client = account_client("analyst")
    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/v1/cases/RC-1042/decisions",
        headers={**ORIGIN, "Idempotency-Key": "pg-triage-1"},
        json={"action": "triage", "note": "Reviewed synthetic data", "version": 1},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "Triaged"
    assert not store.seed(count=510)
    resumed = TestClient(app, cookies={"pt_session": client.cookies["pt_session"]})
    assert resumed.get("/api/v1/session").json()["role"] == "analyst"
    case = resumed.get("/api/v1/cases/RC-1042").json()["case"]
    assert case["timeline"][-1]["kind"] == "triage"
