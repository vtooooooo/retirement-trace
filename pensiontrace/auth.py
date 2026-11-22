"""Server-side accounts, opaque sessions, and database-backed request limits."""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from ipaddress import ip_address
from threading import BoundedSemaphore
from typing import Annotated, NamedTuple
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .db import Store

ROLES = {
    "analyst": "Maya Chen",
    "senior": "Jon Bell",
    "benefits": "Priya Ross",
    "auditor": "Audit reviewer",
}
SESSION_SECONDS = 8 * 3600
PASSWORD_CHECKS = BoundedSemaphore(2)
USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
PASSWORD_HASH = re.compile(r"scrypt:[a-f0-9]{32}:[a-f0-9]{64}")
router = APIRouter(prefix="/api/v1/session")


class HostingConfigurationError(RuntimeError):
    """A configuration error whose message is safe to show in startup logs."""


class Identity(NamedTuple):
    tenant: str
    role: str
    name: str
    username: str


@dataclass(frozen=True)
class Account:
    identity: Identity
    password_hash: str

    @property
    def fingerprint(self):
        return digest(self.password_hash)


class Login(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def scrypt(password: str, salt: bytes):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(password: str):
    if not 16 <= len(password) <= 256:
        raise ValueError("Use a unique password between 16 and 256 characters")
    salt = secrets.token_bytes(16)
    return f"scrypt:{salt.hex()}:{scrypt(password, salt).hex()}"


def hosted():
    return os.getenv("PT_HOSTED") == "1"


def origins():
    default = "" if hosted() else "http://localhost:5173,http://127.0.0.1:5173,http://testserver"
    return [
        origin.strip() for origin in os.getenv("PT_FRONTEND_ORIGINS", default).split(",") if origin.strip()
    ]


def accounts():
    result: dict[str, Account] = {}
    try:
        rows = json.loads(os.getenv("PT_DEMO_ACCOUNTS", "[]"))
        if not isinstance(rows, list) or len(rows) > 40:
            raise ValueError()
        for row in rows:
            username, role, hashed = (row[k] for k in ("username", "role", "password_hash"))
            tenant = row.get("tenant", "demo")
            if (
                not USERNAME.fullmatch(username)
                or username in result
                or role not in ROLES
                or tenant not in {"demo", "qa"}
                or not PASSWORD_HASH.fullmatch(hashed)
            ):
                raise ValueError()
            result[username] = Account(Identity(tenant, role, ROLES[role], username), hashed)
    except (TypeError, ValueError, KeyError, AttributeError):
        raise HostingConfigurationError("PT_DEMO_ACCOUNTS is invalid.") from None
    return result


def is_https_origin(origin: str) -> bool:
    try:
        url = urlsplit(origin)
        port = url.port
    except ValueError:
        return False
    return (
        url.scheme == "https"
        and bool(url.hostname)
        and url.username is None
        and (port is None or port > 0)
        and origin == f"https://{url.netloc}"
        and not any(char.isspace() or char in "*\\%" or ord(char) < 32 for char in origin)
    )


def validate_hosting(store: Store):
    configured = accounts()
    if not hosted():
        return configured

    from psycopg import ProgrammingError
    from psycopg.conninfo import conninfo_to_dict

    errors = []
    if not os.getenv("DATABASE_URL", "").strip():
        errors.append("DATABASE_URL is missing.")
    elif not store.pg:
        errors.append("DATABASE_URL must be a PostgreSQL URI beginning with postgresql:// or postgres://.")
    else:
        try:
            connection = conninfo_to_dict(store.url)
        except ProgrammingError:
            errors.append(
                "DATABASE_URL is not a valid PostgreSQL URI. Copy the full connection URL from Neon."
            )
        else:
            if not connection.get("host"):
                errors.append("DATABASE_URL must specify a PostgreSQL server hostname.")

    edge_secret = os.getenv("PT_EDGE_SECRET", "")
    if not edge_secret.strip():
        errors.append("PT_EDGE_SECRET is missing.")
    elif len(edge_secret) < 32:
        errors.append("PT_EDGE_SECRET must contain at least 32 characters.")

    allowed = origins()
    if not allowed:
        errors.append("PT_FRONTEND_ORIGINS is missing.")
    elif not all(map(is_https_origin, allowed)):
        errors.append(
            "PT_FRONTEND_ORIGINS must contain exact HTTPS origins without paths or trailing slashes."
        )

    missing_roles = ROLES.keys() - {
        a.identity.role for a in configured.values() if a.identity.tenant == "demo"
    }
    if missing_roles:
        errors.append(
            "PT_DEMO_ACCOUNTS is missing roles in the demo tenant: " + ", ".join(sorted(missing_roles)) + "."
        )
    if errors:
        raise HostingConfigurationError("Hosted configuration invalid. " + " ".join(errors))
    return configured


def cookie_name():
    return "__Host-pt_session" if hosted() else "pt_session"


def client_key(request: Request):
    value = request.headers.get("x-pt-client-ip") if hosted() else None
    if value:
        try:
            return str(ip_address(value))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def enforce_limit(scope: str, key: str, maximum: int, period: int):
    now = int(time.time())
    window = now - now % period
    store = Store()
    with store.transaction() as conn:
        # Bounds table growth while retaining the current and preceding windows.
        store.sql(conn, "DELETE FROM request_limits WHERE expires<=?", now)
        row = store.sql(
            conn,
            """INSERT INTO request_limits(scope, subject, bucket, expires, hits) VALUES (?,?,?,?,1)
               ON CONFLICT(scope, subject, bucket) DO UPDATE SET hits=request_limits.hits+1
               WHERE request_limits.hits < ? RETURNING hits""",
            scope,
            digest(key),
            window,
            window + period,
            maximum,
        ).fetchone()
    if not row:
        raise HTTPException(
            429, "Too many requests. Try again later.", headers={"Retry-After": str(window + period - now)}
        )


def principal(request: Request):
    token = request.cookies.get(cookie_name())
    if not token or not re.fullmatch(r"[\w-]{43}", token, flags=re.ASCII):
        raise HTTPException(401, "Sign in to continue")
    store = Store()
    with store.transaction() as conn:
        session = store.sql(
            conn,
            "SELECT username, tenant, role, fingerprint FROM sessions WHERE token_hash=? AND expires>?",
            digest(token),
            int(time.time()),
        ).fetchone()
    account = accounts().get(session["username"]) if session else None
    if (
        not account
        or (session["tenant"], session["role"]) != (account.identity.tenant, account.identity.role)
        or not hmac.compare_digest(session["fingerprint"], account.fingerprint)
    ):
        raise HTTPException(401, "Sign in to continue")
    enforce_limit("api", account.identity.username, 180, 60)
    return account.identity


SessionIdentity = Annotated[Identity, Depends(principal)]


def public_identity(identity: Identity):
    return {"tenant": identity.tenant, "role": identity.role, "name": identity.name}


@router.post("", status_code=200)
def login(body: Login, request: Request, response: Response):
    username = body.username.strip().lower()
    enforce_limit("login-ip", client_key(request), 30, 300)
    enforce_limit("login-account", username, 10, 300)
    account = accounts().get(username)
    stored = account.password_hash if account else f"scrypt:{'0' * 32}:{'0' * 64}"
    _, salt, expected = stored.split(":")
    if not PASSWORD_CHECKS.acquire(timeout=3):
        raise HTTPException(503, "Sign-in is busy. Try again in a moment.", headers={"Retry-After": "3"})
    try:
        valid = hmac.compare_digest(scrypt(body.password, bytes.fromhex(salt)), bytes.fromhex(expected))
    finally:
        PASSWORD_CHECKS.release()
    if not account or not valid:
        raise HTTPException(401, "Invalid username or password")
    token = secrets.token_urlsafe(32)
    store = Store()
    now = int(time.time())
    with store.transaction() as conn:
        store.sql(conn, "DELETE FROM sessions WHERE expires<=?", now)
        old = request.cookies.get(cookie_name())
        if old:
            store.sql(conn, "DELETE FROM sessions WHERE token_hash=?", digest(old))
        ident = account.identity
        store.sql(
            conn,
            "INSERT INTO sessions(token_hash, username, tenant, role, fingerprint, expires) VALUES (?,?,?,?,?,?)",
            digest(token),
            ident.username,
            ident.tenant,
            ident.role,
            account.fingerprint,
            now + SESSION_SECONDS,
        )
    response.set_cookie(
        cookie_name(), token, max_age=SESSION_SECONDS, secure=hosted(), httponly=True, samesite="lax"
    )
    return public_identity(ident)


@router.get("")
def session(identity: SessionIdentity):
    return public_identity(identity)


@router.delete("", status_code=204)
def logout(request: Request):
    token = request.cookies.get(cookie_name())
    if token:
        store = Store()
        with store.transaction() as conn:
            store.sql(conn, "DELETE FROM sessions WHERE token_hash=?", digest(token))
    response = Response(status_code=204)
    response.delete_cookie(cookie_name(), secure=hosted(), httponly=True, samesite="lax")
    return response
