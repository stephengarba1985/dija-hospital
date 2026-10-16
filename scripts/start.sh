#!/bin/bash
set -euo pipefail
root=/workspace/hospital-management
source "$root/scripts/runtime.sh"
if ! pg_ctl -D /workspace/.onboarding/pgdata status >/dev/null; then
  pg_ctl -D /workspace/.onboarding/pgdata -l /workspace/.onboarding/postgres.log -o '-h 127.0.0.1 -p 5432 -k /workspace/.onboarding' -w start
fi
start_service() {
  local service_name="$1" service_port="$2" directory="$3"
  shift 3
  if [ -f "$root/.local/$service_name.pid" ] && kill -0 "$(cat "$root/.local/$service_name.pid")" 2>/dev/null; then
    echo "$service_name is already running."
    return
  fi
  # Do not silently attach to a different process using the desired port.
  "$root/.venv/bin/python" - "$service_port" <<'PY'
import socket, sys
with socket.socket() as sock:
    sock.settimeout(1)
    if sock.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0:
        raise SystemExit(f'Port {sys.argv[1]} is already in use. Inspect that process before starting a duplicate service.')
PY
  (cd "$directory"; nohup "$@" > "$root/.local/$service_name.log" 2>&1 & echo $! > "$root/.local/$service_name.pid")
}
start_service django 8000 "$root/backend" "$root/.venv/bin/python" manage.py runserver 127.0.0.1:8000 --noreload
# Launch Next directly so the PID belongs to the service, rather than npm's shell.
start_service frontend 3100 "$root/frontend" node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3100
"$root/.venv/bin/python" - <<'PY'
import json, time, urllib.request
for endpoint in ('http://127.0.0.1:8000/api/session/', 'http://127.0.0.1:3100/api/session/'):
    for attempt in range(30):
        try:
            with urllib.request.urlopen(endpoint, timeout=5) as response:
                assert 'csrfToken' in json.load(response)
            break
        except Exception:
            if attempt == 29:
                raise SystemExit(f'Readiness check failed for {endpoint}; inspect .local service logs.')
            time.sleep(1)
print('Dija Hospital services passed session readiness checks.')
PY
