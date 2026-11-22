"""Versioned API. Local token-based roles are deliberately limited to synthetic use."""

import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .db import Store, pack

app = FastAPI(title="PensionTrace AI", version="1.0")
logger = logging.getLogger("pensiontrace.audit")
TEAM = {
    "analyst": ("analyst", "Maya Chen"),
    "senior": ("senior", "Jon Bell"),
    "benefits": ("benefits", "Priya Ross"),
    "auditor": ("auditor", "Audit reviewer"),
    "admin": ("admin", "System administrator"),
}
TRANSITIONS = {
    "triage": ("analyst", {"Detected"}, "Triaged"),
    "investigate": ("analyst", {"Triaged", "Awaiting evidence", "Reopened"}, "Under investigation"),
    "await_evidence": ("analyst", {"Under investigation"}, "Awaiting evidence"),
    "request_review": ("analyst", {"Under investigation", "Awaiting evidence"}, "Pending senior review"),
    "approve_review": ("senior", {"Pending senior review"}, "Pending benefits review"),
    "approve_identity": ("senior", {"Pending senior review"}, "Pending benefits review"),
    "reject_identity": ("senior", {"Pending senior review"}, "Under investigation"),
    "resolve": ("benefits", {"Pending benefits review"}, "Resolved"),
    "close": ("benefits", {"Resolved"}, "Closed"),
    "reopen": ("analyst", {"Resolved", "Closed"}, "Reopened"),
}
Command = Literal[
    "triage",
    "investigate",
    "await_evidence",
    "request_review",
    "approve_review",
    "approve_identity",
    "reject_identity",
    "resolve",
    "close",
    "reopen",
    "assign",
    "note",
    "record_action",
    "attach",
]


class Decision(BaseModel):
    action: Command
    note: str = Field(min_length=3, max_length=500, pattern=r"\S")
    version: int = Field(ge=1)
    reference: str | None = Field(default=None, max_length=120)


def principal(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer credential required")
    presented = authorization[7:]
    matched = []
    for role, (_, name) in TEAM.items():
        token = os.environ.get(f"PT_{role.upper()}_TOKEN")
        if token and hmac.compare_digest(presented.encode(), token.encode()):
            matched.append((os.environ.get(f"PT_{role.upper()}_TENANT", "demo"), role, name))
    if len(matched) == 1:
        return matched[0]
    raise HTTPException(401, "Invalid credential")


Identity = Annotated[tuple[str, str, str], Depends(principal)]


@app.get("/health")
def health():
    store = Store()
    try:
        with store.transaction() as conn:
            migrated = store.sql(conn, "SELECT version FROM schema_versions").fetchone()
            if migrated is None:
                raise RuntimeError("No migration recorded")
    except Exception as exc:
        raise HTTPException(503, "Database is unavailable or has not been migrated") from exc
    return {"status": "ok"}


@app.get("/api/v1/session")
def session(identity: Identity):
    tenant, role, name = identity
    return {"tenant": tenant, "role": role, "name": name}


@app.get("/api/v1/workspace")
def workspace(identity: Identity):
    return Store().snapshot(identity[0])


@app.get("/api/v1/participants")
def participants(
    identity: Identity,
    q: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    store = Store()
    with store.transaction() as conn:
        return [
            dict(row)
            for row in store.sql(
                conn,
                """SELECT id,name FROM items WHERE tenant=? AND (LOWER(name) LIKE ? OR LOWER(id) LIKE ?)
                   ORDER BY id LIMIT ? OFFSET ?""",
                identity[0],
                f"%{q.lower()}%",
                f"%{q.lower()}%",
                limit,
                offset,
            )
        ]


@app.get("/api/v1/cases")
def cases(
    identity: Identity,
    state: str | None = Query(None, max_length=50),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    rows = Store().snapshot(identity[0])["cases"]
    return [c for c in rows if not state or c["state"] == state][offset : offset + limit]


def find_case(identity, case_id):
    data = Store().snapshot(identity[0])
    for case in data["cases"]:
        if case["id"] == case_id:
            return case, data
    raise HTTPException(404, "Case not found")


@app.get("/api/v1/cases/{case_id}")
def detail(case_id: str, identity: Identity):
    case, data = find_case(identity, case_id)
    matches = [m for m in data["matches"] if m["person"] == case["person"]]
    refs = set(case["evidence"]) | {r for m in matches for r in (m["left"], m["right"])}
    return {"case": case, "matches": matches, "evidence": {r: data["evidence"][r] for r in sorted(refs)}}


@app.get("/api/v1/cases/{case_id}/audit")
def audit(case_id: str, identity: Identity):
    return Response(
        pack(detail(case_id, identity)),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{case_id}-audit.json"'},
    )


@app.post("/api/v1/cases/{case_id}/decisions")
def decision(
    case_id: str,
    body: Decision,
    identity: Identity,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=120)],
):
    tenant, role, actor = identity
    store = Store()
    with store.transaction() as conn:
        if not store.pg:
            store.sql(conn, "BEGIN IMMEDIATE")
        lock = " FOR UPDATE" if store.pg else ""
        row = store.sql(
            conn, "SELECT * FROM cases WHERE tenant=? AND id=?" + lock, tenant, case_id
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Case not found")
        previous = store.sql(
            conn,
            "SELECT actor,payload FROM events WHERE tenant=? AND case_id=? AND idem=?",
            tenant,
            case_id,
            idempotency_key,
        ).fetchone()
        if previous:
            saved = json.loads(previous["payload"])
            if previous["actor"] != actor or saved.get("request") != body.model_dump():
                raise HTTPException(409, "Idempotency key already used")
            return saved
        state, assignee, requester = row["state"], row["assignee"], row["requester"]
        if body.version != row["version"]:
            raise HTTPException(409, "Case has changed. Reload before recording a decision.")
        if body.action in TRANSITIONS:
            required, current, target = TRANSITIONS[body.action]
            if role != required or (role in {"senior", "benefits"} and actor == requester):
                raise HTTPException(403, "Decision requires an independent authorized reviewer")
            if state not in current:
                raise HTTPException(409, "Transition is not available in this state")
            if body.action == "request_review":
                requester = actor
            if body.action in {"approve_review", "approve_identity", "reject_identity"}:
                raw_alert = store.sql(
                    conn, "SELECT payload FROM alerts WHERE tenant=? AND id=?", tenant, row["alert"]
                ).fetchone()
                alert = json.loads(raw_alert["payload"])
                if body.action == "approve_review" and alert["kind"] == "identifier":
                    raise HTTPException(422, "An identifier conflict requires an explicit identity decision")
                if body.action in {"approve_identity", "reject_identity"}:
                    linked = store.sql(
                        conn,
                        "SELECT right_id FROM candidates WHERE tenant=? AND person=? AND id=?",
                        tenant,
                        alert["person"],
                        body.reference,
                    ).fetchone()
                    if not linked:
                        raise HTTPException(422, "Select a candidate belonging to this case")
                    if alert["kind"] == "identifier" and linked["right_id"] not in alert["conflicting"]:
                        raise HTTPException(422, "Select the candidate cited in the identifier conflict")
            state = target
        elif role not in {"analyst", "senior"}:
            raise HTTPException(403, "Role cannot change the investigation record")
        elif state in {"Resolved", "Closed"}:
            raise HTTPException(409, "Reopen this case before changing the investigation record")
        elif body.action == "assign":
            names = {TEAM[r][1] for r in ("analyst", "senior")}
            if body.reference not in names:
                raise HTTPException(422, "Unknown investigation assignee")
            assignee = body.reference
        elif body.action == "record_action":
            # Resolve references against the case's own persisted evidence.
            case, _ = find_case(identity, case_id)
            if body.reference not in {a["name"] for a in case["actions"]}:
                raise HTTPException(422, "Action is not eligible for this case")
        elif body.action == "attach":
            if not body.reference:
                raise HTTPException(422, "Internal document reference required")
        version = row["version"] + 1
        changed = store.sql(
            conn,
            """UPDATE cases SET state=?,assignee=?,requester=?,version=?
                                    WHERE tenant=? AND id=? AND version=?""",
            state,
            assignee,
            requester,
            version,
            tenant,
            case_id,
            row["version"],
        ).rowcount
        if not changed:
            raise HTTPException(409, "Case changed concurrently")
        event = dict(
            state=state,
            note=body.note,
            version=version,
            reference=body.reference,
            request=body.model_dump(),
            assignee=assignee,
        )
        store.sql(
            conn,
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
            tenant,
            case_id,
            version,
            actor,
            body.action,
            datetime.now(UTC).isoformat(),
            idempotency_key,
            pack(event),
        )
        logger.info(
            "case_decision",
            extra={"case_id": case_id, "decision": body.action, "role": role, "revision": version},
        )
        return event
