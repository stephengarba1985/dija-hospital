#!/bin/bash
set -euo pipefail
root=/workspace/hospital-management
pgroot=/workspace/.onboarding
mkdir -p "$root/.local" "$pgroot/pg"
chmod 700 "$root/.local"
if [ ! -x "$pgroot/pg/usr/lib/postgresql/17/bin/postgres" ]; then
  # Debian's signed package indexes and apt-verified package hashes remain enabled.
  mkdir -p "$root/.local/apt/lists/partial" "$root/.local/apt/cache/archives/partial" "$root/.local/postgres-debs"
  printf '%s\n' 'deb https://deb.debian.org/debian trixie main' > "$root/.local/apt/sources.list"
  apt_options=(-o "Dir::Etc::sourcelist=$root/.local/apt/sources.list" -o Dir::Etc::sourceparts=- -o "Dir::State::lists=$root/.local/apt/lists" -o "Dir::Cache=$root/.local/apt/cache")
  apt-get "${apt_options[@]}" update
  cd "$root/.local/postgres-debs"
  apt-get "${apt_options[@]}" download postgresql-17 postgresql-client-17 libpq5 libllvm19 libxml2 libicu76 libssl3t64 liblz4-1 libzstd1 libreadline8t64 libxslt1.1
  for package in ./*.deb; do dpkg-deb -x "$package" "$pgroot/pg"; done
fi
if [ ! -x "$root/.venv/bin/python" ]; then python3 -m venv "$root/.venv"; fi
"$root/.venv/bin/pip" install --cache-dir "$root/.local/pip-cache" -r "$root/backend/requirements.txt"
if [ ! -f "$root/.local/django-secret" ]; then
  (umask 077; "$root/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(64), end="")' > "$root/.local/django-secret")
fi
source "$root/scripts/runtime.sh"
if [ ! -f "$pgroot/pgdata/PG_VERSION" ]; then
  initdb -D "$pgroot/pgdata" --auth-local=trust --auth-host=trust --no-locale -E UTF8
fi
if ! pg_ctl -D "$pgroot/pgdata" status >/dev/null; then
  pg_ctl -D "$pgroot/pgdata" -l "$pgroot/postgres.log" -o '-h 127.0.0.1 -p 5432 -k /workspace/.onboarding' -w start
fi
if ! psql -h 127.0.0.1 -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='dija_hospital'" | rg -q '^1$'; then
  createdb -h 127.0.0.1 dija_hospital
fi
cd "$root/backend"
"$root/.venv/bin/python" manage.py migrate --noinput
"$root/.venv/bin/python" manage.py bootstrap_hospital
"$root/.venv/bin/python" manage.py create_local_admin
"$root/.venv/bin/python" manage.py check
cd "$root/frontend"
npm ci --cache /workspace/.npm
