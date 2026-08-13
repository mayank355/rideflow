#!/bin/sh
# Runs pending Alembic migrations, then starts the app. This is the
# container's actual startup sequence — migrations must complete before
# uvicorn accepts traffic, otherwise the app could serve requests against
# a database schema it doesn't expect.
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
