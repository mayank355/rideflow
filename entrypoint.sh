#!/bin/sh
# Runs pending Alembic migrations, then starts the app.
set -e

alembic upgrade head

# Railway (and most PaaS providers) inject a PORT env var and expect the
# app to bind to it dynamically -- the port isn't fixed at 8000 in their
# environment. Locally, PORT is unset, so we fall back to 8000, matching
# docker-compose.yml's port mapping. ${PORT:-8000} means "use $PORT if
# set, otherwise use 8000" -- one entrypoint works correctly in both
# environments without needing separate scripts.
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
