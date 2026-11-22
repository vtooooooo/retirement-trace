import json
import os
import subprocess
import sys

import pytest

from pensiontrace.auth import ROLES, HostingConfigurationError, validate_hosting
from pensiontrace.db import Store

NEON = (
    "postgresql://fixture_user:fixture%40password@ep-fixture-pooler.us-east-2.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)
HASH = "scrypt:" + "a" * 32 + ":" + "b" * 64
EDGE = "fixture-edge-secret-with-32-characters"


@pytest.fixture
def hosted_config(monkeypatch):
    values = {
        "PT_HOSTED": "1",
        "DATABASE_URL": NEON,
        "PT_EDGE_SECRET": EDGE,
        "PT_FRONTEND_ORIGINS": "https://pensiontrace.pages.dev",
        "PT_DEMO_ACCOUNTS": json.dumps(
            [{"username": f"fixture-{role}", "role": role, "password_hash": HASH} for role in ROLES]
        ),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.mark.parametrize("scheme", ["postgresql://", "postgres://"])
def test_accepts_neon_pooler_without_connecting(hosted_config, monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", NEON.replace("postgresql://", scheme, 1))
    store = Store()
    assert store.pg
    assert {account.identity.role for account in validate_hosting(store).values()} == set(ROLES)


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
        ("DATABASE_URL", "", "DATABASE_URL is missing."),
        ("DATABASE_URL", f'"{NEON}"', "DATABASE_URL must be a PostgreSQL URI"),
        (
            "DATABASE_URL",
            NEON + "&unknown_option=fixture-credential",
            "DATABASE_URL is not a valid PostgreSQL URI",
        ),
        ("DATABASE_URL", "postgresql:///neondb", "DATABASE_URL must specify a PostgreSQL server hostname."),
        ("PT_EDGE_SECRET", "", "PT_EDGE_SECRET is missing."),
        ("PT_EDGE_SECRET", "short-fixture", "PT_EDGE_SECRET must contain at least 32 characters."),
        ("PT_FRONTEND_ORIGINS", "", "PT_FRONTEND_ORIGINS is missing."),
        (
            "PT_FRONTEND_ORIGINS",
            "https://pensiontrace.pages.dev/",
            "PT_FRONTEND_ORIGINS must contain exact HTTPS origins",
        ),
        (
            "PT_FRONTEND_ORIGINS",
            "https://[fixture-credential",
            "PT_FRONTEND_ORIGINS must contain exact HTTPS origins",
        ),
        (
            "PT_FRONTEND_ORIGINS",
            "https://fixture-user:fixture-credential@pensiontrace.pages.dev",
            "PT_FRONTEND_ORIGINS must contain exact HTTPS origins",
        ),
        ("PT_DEMO_ACCOUNTS", "fixture-invalid-json", "PT_DEMO_ACCOUNTS is invalid."),
    ],
)
def test_reports_only_the_failing_setting(hosted_config, monkeypatch, setting, value, expected):
    monkeypatch.setenv(setting, value)
    with pytest.raises(HostingConfigurationError) as captured:
        validate_hosting(Store())
    message = str(captured.value)
    assert expected in message
    for key in hosted_config.keys() - {setting, "PT_HOSTED"}:
        assert key not in message
    assert "fixture" not in message
    assert HASH not in message


def test_cli_reports_multiple_failures_and_demo_only_roles_safely(hosted_config):
    rows = json.loads(hosted_config["PT_DEMO_ACCOUNTS"])
    rows[-1]["tenant"] = "qa"
    process = subprocess.run(
        [sys.executable, "-m", "pensiontrace.hosting", "initialize"],
        env={
            **os.environ,
            "PT_DEMO_ACCOUNTS": json.dumps(rows),
            "PT_EDGE_SECRET": "fixture-short",
            "DATABASE_URL": NEON + "&unknown_option=fixture-credential",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 1
    assert process.stdout == ""
    assert "DATABASE_URL is not a valid PostgreSQL URI" in process.stderr
    assert "PT_EDGE_SECRET must contain at least 32 characters" in process.stderr
    assert "PT_DEMO_ACCOUNTS is missing roles in the demo tenant: auditor." in process.stderr
    assert "PT_FRONTEND_ORIGINS" not in process.stderr
    for private in ("fixture", EDGE, HASH, "Traceback"):
        assert private not in process.stderr
