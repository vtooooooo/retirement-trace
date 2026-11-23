import sys

import pytest
from psycopg import OperationalError
from psycopg.errors import ConnectionTimeout, InvalidCatalogName, InvalidPassword

from pensiontrace import hosting

PRIVATE = "postgresql://fixture-user:fixture-password@fixture-host.example/fixture-db"


@pytest.mark.parametrize(
    ("error_class", "detail", "category"),
    [
        (InvalidPassword, "unclassified", "authentication failed"),
        (OperationalError, 'password authentication failed for user "fixture-user"', "authentication failed"),
        (OperationalError, 'failed to resolve host "fixture-host.example"', "DNS resolution failed"),
        (
            OperationalError,
            "could not translate host name: Name or service not known",
            "DNS resolution failed",
        ),
        (ConnectionTimeout, "unclassified", "connection timeout or network failure"),
        (OperationalError, "Connection refused", "connection timeout or network failure"),
        (OperationalError, "SSL error: certificate verify failed", "TLS/certificate failure"),
        (
            OperationalError,
            "channel binding required, but server did not offer it",
            "TLS/certificate failure",
        ),
        (InvalidCatalogName, "unclassified", "database not found"),
        (OperationalError, 'database "fixture-db" does not exist', "database not found"),
        (OperationalError, "provider reported an unrecognized error", "other connection error"),
    ],
)
def test_diagnostic_uses_only_fixed_text(error_class, detail, category):
    diagnostic = hosting.postgres_startup_diagnostic(error_class(f"{detail}: {PRIVATE}"))
    assert diagnostic.startswith(category + ". ")
    assert "fixture-" not in diagnostic
    assert PRIVATE not in diagnostic


@pytest.mark.parametrize(("error_class", "delays"), [(OperationalError, [1, 2]), (InvalidCatalogName, [])])
def test_startup_preserves_retry_behavior_and_redacts_output(monkeypatch, capsys, error_class, delays):
    monkeypatch.setattr(sys, "argv", ["hosting", "initialize"])
    monkeypatch.setenv("DATABASE_URL", PRIVATE)
    monkeypatch.setattr(hosting, "validate_hosting", lambda store: {})
    sleeps = []
    attempts = []

    def fail(store, tenants):
        attempts.append(tenants)
        raise error_class(f'database "fixture-db" does not exist: {PRIVATE}')

    monkeypatch.setattr(hosting.time, "sleep", sleeps.append)
    monkeypatch.setattr(hosting, "initialize", fail)
    with pytest.raises(SystemExit) as stopped:
        hosting.main()
    assert stopped.value.code == 1
    assert sleeps == delays
    assert attempts == [["demo"]] * (len(delays) + 1)
    stdout, stderr = capsys.readouterr()
    assert stdout.count("Waiting for PostgreSQL to accept connections: database not found.") == len(delays)
    assert "PostgreSQL startup failed: database not found." in stderr
    assert "fixture-" not in stdout + stderr
    assert "Traceback" not in stdout + stderr
