#!/bin/bash
# Local development only. The database and secrets are separate from the old project.
DIJA_ROOT=/workspace/hospital-management
export PATH=/workspace/.onboarding/pg/usr/lib/postgresql/17/bin:$PATH
export LD_LIBRARY_PATH=/workspace/.onboarding/pg/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export DATABASE_URL=postgresql://agent@127.0.0.1:5432/dija_hospital
export DJANGO_SECRET_KEY=$(cat "$DIJA_ROOT/.local/django-secret")
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
export CSRF_TRUSTED_ORIGINS=http://localhost:3100,http://127.0.0.1:3100
