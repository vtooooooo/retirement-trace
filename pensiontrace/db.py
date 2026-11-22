"""Versioned SQL schema shared by PostgreSQL and the SQLite developer profile."""

import json
import os
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .engine import AS_OF, VERSION, detect, evaluate, evaluate_actions, generate, rank

DDL = (
    "CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY)",
    """CREATE TABLE IF NOT EXISTS items (
        tenant TEXT NOT NULL REFERENCES tenants(id), id TEXT NOT NULL, name TEXT NOT NULL,
        PRIMARY KEY (tenant,id))""",
    """CREATE TABLE IF NOT EXISTS evidence (
        tenant TEXT NOT NULL, id TEXT NOT NULL, person TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (tenant,id), FOREIGN KEY (tenant,person) REFERENCES items(tenant,id))""",
    "CREATE INDEX IF NOT EXISTS evidence_by_person ON evidence(tenant,person,kind)",
    """CREATE TABLE IF NOT EXISTS candidates (
        tenant TEXT NOT NULL, id TEXT NOT NULL, person TEXT NOT NULL, left_id TEXT NOT NULL,
        right_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (tenant,id),
        UNIQUE (tenant,left_id,right_id), FOREIGN KEY (tenant,person) REFERENCES items(tenant,id),
        FOREIGN KEY (tenant,left_id) REFERENCES evidence(tenant,id),
        FOREIGN KEY (tenant,right_id) REFERENCES evidence(tenant,id))""",
    "CREATE INDEX IF NOT EXISTS candidates_by_person ON candidates(tenant,person)",
    """CREATE TABLE IF NOT EXISTS alerts (
        tenant TEXT NOT NULL, id TEXT NOT NULL, person TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (tenant,id), FOREIGN KEY (tenant,person) REFERENCES items(tenant,id))""",
    """CREATE TABLE IF NOT EXISTS cases (
        tenant TEXT NOT NULL, id TEXT NOT NULL, alert TEXT NOT NULL, state TEXT NOT NULL, assignee TEXT,
        requester TEXT, version INTEGER NOT NULL, created TEXT NOT NULL,
        PRIMARY KEY (tenant,id), UNIQUE (tenant,alert), FOREIGN KEY (tenant,alert) REFERENCES alerts(tenant,id))""",
    """CREATE TABLE IF NOT EXISTS events (
        tenant TEXT NOT NULL, case_id TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL,
        kind TEXT NOT NULL, at TEXT NOT NULL, idem TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (tenant,case_id,version), UNIQUE (tenant,case_id,idem),
        FOREIGN KEY (tenant,case_id) REFERENCES cases(tenant,id))""",
    """CREATE TABLE IF NOT EXISTS benchmarks (
        tenant TEXT PRIMARY KEY REFERENCES tenants(id), payload TEXT NOT NULL)""",
)


SESSION_DDL = (
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, tenant TEXT NOT NULL REFERENCES tenants(id),
        role TEXT NOT NULL, fingerprint TEXT NOT NULL, expires BIGINT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires)",
    """CREATE TABLE IF NOT EXISTS request_limits (
        scope TEXT NOT NULL, subject TEXT NOT NULL, bucket BIGINT NOT NULL,
        expires BIGINT NOT NULL, hits INTEGER NOT NULL, PRIMARY KEY (scope,subject,bucket))""",
    "CREATE INDEX IF NOT EXISTS request_limits_expiry ON request_limits(expires)",
)


def pack(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class Store:
    def __init__(self):
        self.url = os.environ.get("DATABASE_URL", "sqlite:///runtime/pensiontrace.db")
        self.pg = self.url.startswith(("postgresql://", "postgres://"))

    @contextmanager
    def transaction(self):
        conn: Any
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row

            sslmode = "require" if os.getenv("PT_HOSTED") == "1" else "prefer"
            conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5, sslmode=sslmode)
        else:
            path = Path(self.url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def sql(self, conn, query, *params):
        return conn.execute(query.replace("?", "%s") if self.pg else query, params)

    def bulk(self, conn, query, rows):
        cursor = conn.cursor()
        try:
            cursor.executemany(query.replace("?", "%s") if self.pg else query, rows)
        finally:
            cursor.close()

    def migrate(self):
        with self.transaction() as conn:
            if self.pg:
                self.sql(conn, "SELECT pg_advisory_xact_lock(621946190)")
            else:
                self.sql(conn, "BEGIN IMMEDIATE")
            self.sql(conn, DDL[0])
            for version, statements in ((1, DDL[1:]), (2, SESSION_DDL)):
                if self.sql(conn, "SELECT version FROM schema_versions WHERE version=?", version).fetchone():
                    continue
                for statement in statements:
                    self.sql(conn, statement)
                self.sql(conn, "INSERT INTO schema_versions VALUES (?)", version)

    def seed(self, seed=73, count=6600, tenant="demo"):
        self.migrate()
        with self.transaction() as conn:
            if not self.sql(conn, "INSERT INTO tenants VALUES (?) ON CONFLICT DO NOTHING", tenant).rowcount:
                return False
            people, evidence, truth, expected = generate(seed, count)
            # Scoring and operational links use only source claims. The hidden labels
            # are consumed by fit/evaluation and are never stored or exported.
            matches, benchmark = evaluate(evidence, truth)
            alerts = detect(evidence)
            groups = defaultdict(list)
            for row in evidence:
                groups[row.get("claimed_case_ref") or row["person"]].append(row)
            benchmark["investigation"] = evaluate_actions(alerts, groups, seed)
            actual = {(a["person"], a["kind"]) for a in alerts}
            labels = set(expected.items())
            benchmark["rules"] = dict(
                tp=len(actual & labels), fp=len(actual - labels), fn=len(labels - actual)
            )
            benchmark["ingestion"] = dict(
                seed=seed,
                participants=len(people),
                sources=sum(r["kind"] == "identity" for r in evidence),
                records=len(evidence),
                alerts=len(alerts),
                by_kind={
                    k: sum(r["kind"] == k for r in evidence) for k in sorted({r["kind"] for r in evidence})
                },
            )
            self.bulk(
                conn, "INSERT INTO items VALUES (?,?,?)", [(tenant, p["id"], p["name"]) for p in people]
            )
            self.bulk(
                conn,
                "INSERT INTO evidence VALUES (?,?,?,?,?)",
                [(tenant, r["id"], r["person"], r["kind"], pack(r)) for r in evidence],
            )
            self.bulk(
                conn,
                "INSERT INTO candidates VALUES (?,?,?,?,?,?)",
                [(tenant, m["id"], m["person"], m["left"], m["right"], pack(m)) for m in matches],
            )
            self.bulk(
                conn,
                "INSERT INTO alerts VALUES (?,?,?,?)",
                [(tenant, a["id"], a["person"], pack(a)) for a in alerts],
            )
            for i, alert in enumerate(alerts):
                uid = f"RC-{1042 + i}"
                state = ("Detected", "Triaged", "Under investigation", "Awaiting evidence")[i % 4]
                assignee = None if state == "Detected" else ("Maya Chen", "Jon Bell", "Priya Ross")[i % 3]
                created = f"2026-09-{25 - (i * 7) % 24:02}"
                self.sql(
                    conn,
                    "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)",
                    tenant,
                    uid,
                    alert["id"],
                    state,
                    assignee,
                    None,
                    1,
                    created,
                )
                self.sql(
                    conn,
                    "INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                    tenant,
                    uid,
                    1,
                    "Synthetic ingestion",
                    "detected",
                    created,
                    "seed",
                    pack(
                        dict(state=state, note=alert["title"], version=VERSION, evidence=alert["supporting"])
                    ),
                )
            self.sql(conn, "INSERT INTO benchmarks VALUES (?,?)", tenant, pack(benchmark))
        return True

    def snapshot(self, tenant, limit=None, *, public=False):
        with self.transaction() as conn:

            def read(query, *params):
                return self.sql(conn, query, tenant, *params).fetchall()

            raw = read("""SELECT c.*, a.person, a.payload, i.name FROM cases c JOIN alerts a
                       ON a.tenant=c.tenant AND a.id=c.alert JOIN items i ON i.tenant=a.tenant AND i.id=a.person
                       WHERE c.tenant=? ORDER BY c.id""")
            cases = [
                dict(
                    id=r["id"],
                    person=r["person"],
                    name=r["name"],
                    alert=json.loads(r["payload"]),
                    state=r["state"],
                    assignee=r["assignee"],
                    created=r["created"],
                    version=r["version"],
                )
                for r in raw
            ]
            if public and any(c["version"] != 1 for c in cases):
                raise ValueError("Public export requires a pristine synthetic database")
            metrics = self.metrics(cases)
            selected = cases[:limit]
            ids = {c["id"] for c in selected}
            people = {c["person"] for c in selected}
            matches = [
                json.loads(r["payload"])
                for r in read("SELECT payload FROM candidates WHERE tenant=? ORDER BY id")
            ]
            matches = [m for m in matches if m["person"] in people]
            claimed = {ref for c in selected for ref in c["alert"]["conflicting"]}
            matches.sort(
                key=lambda m: (m["right"] not in claimed, m["status"] != "proposed", -m["score"], m["id"])
            )
            top: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for m in matches:
                if len(top[m["person"]]) < 8:
                    top[m["person"]].append(m)
            matches = [m for values in top.values() for m in values]
            refs = {ref for m in matches for ref in (m["left"], m["right"])}
            refs.update(ref for c in selected for ref in c["alert"]["supporting"])
            evidence = {
                r["id"]: json.loads(r["payload"])
                for r in read("SELECT * FROM evidence WHERE tenant=? ORDER BY id")
                if r["person"] in people or r["id"] in refs
            }
            events = defaultdict(list)
            for r in read(
                "SELECT * FROM events WHERE tenant=? ORDER BY version",
            ):
                if r["case_id"] in ids:
                    events[r["case_id"]].append(
                        {**{k: r[k] for k in ("actor", "kind", "at", "version")}, **json.loads(r["payload"])}
                    )
            benchmark = read("SELECT payload FROM benchmarks WHERE tenant=?")
            resolutions = read("SELECT at FROM events WHERE tenant=? AND kind='resolve' ORDER BY at")
            metrics["throughput"] = dict(Counter(row["at"][:7] for row in resolutions))
            metrics["reviewed_identities"] = self.sql(
                conn,
                """SELECT COUNT(DISTINCT case_id) AS n
                FROM events WHERE tenant=? AND kind='approve_identity'""",
                tenant,
            ).fetchone()["n"]
        by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in evidence.values():
            if row["person"]:
                by_person[row["person"]].append(row)
        for c in selected:
            rows_by_id = {r["id"]: r for r in by_person[c["person"]]}
            rows_by_id.update({ref: evidence[ref] for ref in c["alert"]["supporting"]})
            rows = [rows_by_id[ref] for ref in sorted(rows_by_id)]
            c["actions"] = rank(c["alert"], rows)
            c["evidence"] = [r["id"] for r in rows]
            c["timeline"] = events[c["id"]]
        return dict(
            as_of=AS_OF,
            version=VERSION,
            cases=selected,
            metrics=metrics,
            matches=matches,
            evidence=evidence,
            benchmark=json.loads(benchmark[0]["payload"]) if benchmark else {},
        )

    @staticmethod
    def metrics(cases):
        from datetime import date

        open_cases = [c for c in cases if c["state"] not in {"Resolved", "Closed"}]
        ages = [(date.fromisoformat(AS_OF) - date.fromisoformat(c["created"])).days for c in open_cases]

        return dict(
            total=len(cases),
            open=len(open_cases),
            review=sum(c["state"].startswith("Pending") for c in cases),
            high=sum(c["alert"]["severity"] == "high" for c in open_cases),
            awaiting=sum(c["state"] == "Awaiting evidence" for c in open_cases),
            uncashed=sum(c["alert"]["kind"] == "uncashed" for c in open_cases),
            resolved=len(cases) - len(open_cases),
            average_age=round(sum(ages) / max(1, len(ages)), 1),
            aging={
                "0–7 days": sum(a <= 7 for a in ages),
                "8–14 days": sum(7 < a <= 14 for a in ages),
                "15–30 days": sum(14 < a <= 30 for a in ages),
                "31+ days": sum(a > 30 for a in ages),
            },
            statuses=Counter(c["state"] for c in cases),
            categories=Counter(c["alert"]["title"] for c in cases),
            workload=Counter(c["assignee"] or "Unassigned" for c in open_cases),
        )
