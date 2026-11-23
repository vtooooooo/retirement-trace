"""Deployment initialization and a local password-hash utility."""

import argparse
import getpass
import re
import time

from .auth import HostingConfigurationError, hash_password, validate_hosting
from .db import Store

# libpq connection failures often have no SQLSTATE. These markers select fixed
# messages only. Never emit provider text, which can include connection details.
_CONNECTION_MARKERS = (
    ("database not found", r"database [^\n]+ does not exist|database not found|unknown database"),
    (
        "authentication failed",
        r"authentication failed|no password supplied|password is required|role [^\n]+ does not exist"
        r"|no pg_hba\.conf entry|invalid password|(?:password|authentication) has expired",
    ),
    (
        "DNS resolution failed",
        r"could not translate host name|could not resolve|failed to resolve|name resolution"
        r"|name or service not known|nodename nor servname|no address associated with hostname",
    ),
    (
        "TLS/certificate failure",
        r"\b(?:ssl|tls) (?:error|failure|required|handshake|connection|certificate|root certificate)"
        r"|server does not support ssl|certificate[^\n]*(?:verify|verification|hostname|expired|does not)"
        r"|root certificate file|channel binding|hostname mismatch|sslrootcert",
    ),
    (
        "connection timeout or network failure",
        r"timeout expired|timed out|connection timeout|connection refused|network is unreachable"
        r"|no route to host|connection reset|server closed the connection|broken pipe|connection aborted",
    ),
)
_CONNECTION_GUIDANCE = {
    "database not found": "Check that the database selected for the Neon connection still exists.",
    "authentication failed": "Copy a fresh connection URL for the selected Neon role and verify its password.",
    "DNS resolution failed": "Copy the current pooled connection URL from Neon and check endpoint availability.",
    "TLS/certificate failure": "Check Neon TLS support, the certificate trust store, and channel binding.",
    "connection timeout or network failure": "Check Neon project status and Render outbound network access.",
    "other connection error": "Check the Neon project, its pooled connection settings, and provider status.",
}


def postgres_startup_diagnostic(exc):
    from psycopg.errors import ConnectionTimeout

    state = exc.sqlstate or ""
    if state == "3D000":
        category = "database not found"
    elif state.startswith("28"):
        category = "authentication failed"
    elif isinstance(exc, ConnectionTimeout):
        category = "connection timeout or network failure"
    else:
        # When psycopg combines several connection attempts, classify their
        # primary error, which appears before the additional attempt details.
        message = str(exc).split("\nMultiple connection attempts failed.", 1)[0].lower()
        category = next(
            (kind for kind, pattern in _CONNECTION_MARKERS if re.search(pattern, message)),
            "connection timeout or network failure" if state.startswith("08") else "other connection error",
        )
    return f"{category}. {_CONNECTION_GUIDANCE[category]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["initialize", "hash-password"])
    args = parser.parse_args()
    if args.command == "hash-password":
        first = getpass.getpass("Demo account password: ")
        if first != getpass.getpass("Confirm password: "):
            parser.error("Passwords did not match")
        print(hash_password(first))
        return
    store = Store()
    try:
        config = validate_hosting(store)
    except HostingConfigurationError as exc:
        parser.exit(1, f"{exc}\n")
    tenants = sorted({"demo", *(account.identity.tenant for account in config.values())})
    for attempt in range(3):
        try:
            initialize(store, tenants)
            return
        except Exception as exc:
            from psycopg import Error, OperationalError

            if not store.pg or not isinstance(exc, Error):
                raise
            diagnostic = postgres_startup_diagnostic(exc)
            if not isinstance(exc, OperationalError) or attempt == 2:
                parser.exit(1, f"PostgreSQL startup failed: {diagnostic}\n")
            print(f"Waiting for PostgreSQL to accept connections: {diagnostic}", flush=True)
            time.sleep(2**attempt)


def initialize(store, tenants):
    if store.initialized(tenants):
        print("Existing synthetic data and schema are ready.")
        return
    store.migrate()
    for tenant in tenants:
        seeded = store.seed(tenant=tenant, migrated=True)
        print(f"Synthetic tenant {tenant}: {'initialized' if seeded else 'already initialized'}")
    if not store.initialized(tenants):
        raise RuntimeError("Existing tenant data is incomplete. Restore from a known good database.")


if __name__ == "__main__":
    main()
