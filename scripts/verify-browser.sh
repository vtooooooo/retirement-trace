#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
scratch=$(mktemp -d)
api_pid=
web_pid=
cleanup() {
  if [[ -n $api_pid ]]; then kill "$api_pid" 2>/dev/null || true; fi
  if [[ -n $web_pid ]]; then kill "$web_pid" 2>/dev/null || true; fi
  rm -rf "$scratch"
}
trap cleanup EXIT
export DATABASE_URL=${PT_BROWSER_DATABASE_URL:-sqlite:///$scratch/browser.db}
web_port=${PT_TEST_WEB_PORT:-5173}
api_port=${PT_TEST_API_PORT:-8000}
export PT_E2E_LOCAL_URL=http://127.0.0.1:$web_port
export PT_E2E_API_URL=http://127.0.0.1:$api_port
export PT_LOCAL_API_TARGET=$PT_E2E_API_URL
export PT_HOSTED=0 PT_FRONTEND_ORIGINS=$PT_E2E_LOCAL_URL
export PT_RESTART_PROOF=$scratch/restart.json
python - <<'PY' > "$scratch/accounts"
import json
import secrets
import shlex
from pensiontrace.auth import ROLES, hash_password
accounts = []
for role in ROLES:
    password = secrets.token_urlsafe(24)
    accounts.append({"username": role, "role": role, "password_hash": hash_password(password)})
    print(f"export PT_E2E_{role.upper()}_USER={role}")
    print(f"export PT_E2E_{role.upper()}_PASSWORD={shlex.quote(password)}")
print("export PT_DEMO_ACCOUNTS=" + shlex.quote(json.dumps(accounts)))
PY
source "$scratch/accounts"
python -m pensiontrace.hosting initialize
start_api() {
  python -m uvicorn pensiontrace.api:app --host 127.0.0.1 --port "$api_port" &
  api_pid=$!
  curl -fsS --retry 15 --retry-connrefused --retry-delay 1 "$PT_E2E_API_URL/ready"
  kill -0 "$api_pid"
}
start_api
node web/node_modules/vite/bin/vite.js web --config web/vite.config.ts --host 127.0.0.1 --port "$web_port" --strictPort &
web_pid=$!
curl -fsS --retry 15 --retry-connrefused --retry-delay 1 "$PT_E2E_LOCAL_URL/" >/dev/null
kill -0 "$web_pid"
npm --prefix web test -- --grep-invert "backend process restart"
kill "$api_pid"
wait "$api_pid" || true
api_pid=
python -m pensiontrace.hosting initialize
start_api
PT_VERIFY_RESTART_PROOF=$PT_RESTART_PROOF npm --prefix web test -- --grep "backend process restart"
