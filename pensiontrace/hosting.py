"""Deployment initialization and a local password-hash utility."""

import argparse
import getpass
import time

from .auth import hash_password, validate_hosting
from .db import Store


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
    config = validate_hosting(store)
    tenants = sorted({"demo", *(account.identity.tenant for account in config.values())})
    for attempt in range(3):
        try:
            initialize(store, tenants)
            return
        except Exception as exc:
            # Never print connection errors that might contain provider details.
            from psycopg import OperationalError

            if not store.pg or not isinstance(exc, OperationalError):
                raise
            if attempt == 2:
                parser.exit(
                    1, "PostgreSQL startup failed. Check DATABASE_URL, TLS, and Neon project status.\n"
                )
            print("Waiting for PostgreSQL to accept connections.", flush=True)
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
