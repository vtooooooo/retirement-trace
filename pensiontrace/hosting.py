"""Deployment initialization and a local password-hash utility."""

import argparse
import getpass

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
    store.migrate()
    for tenant in sorted({"demo", *(account.identity.tenant for account in config.values())}):
        seeded = store.seed(tenant=tenant)
        print(f"Synthetic tenant {tenant}: {'initialized' if seeded else 'already initialized'}")


if __name__ == "__main__":
    main()
