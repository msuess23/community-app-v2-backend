#!/usr/bin/env bash
set -euo pipefail

# Offline verification should not depend on a developer-specific .env file.
export PROJECT_NAME="${PROJECT_NAME:-Community Backend Verification}"
export BASE_URL="${BASE_URL:-/api/v1}"
export SECRET_KEY="${SECRET_KEY:-verification-secret-key-that-is-long-enough}"
export ACCESS_TOKEN_EXPIRE_MINUTES="${ACCESS_TOKEN_EXPIRE_MINUTES:-15}"
export REFRESH_TOKEN_EXPIRE_DAYS="${REFRESH_TOKEN_EXPIRE_DAYS:-7}"
export POSTGRES_USER="${POSTGRES_USER:-verification}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-verification}"
export POSTGRES_DB="${POSTGRES_DB:-verification}"
export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export ENVIRONMENT="${ENVIRONMENT:-test}"
export RUN_SEED_ON_STARTUP="${RUN_SEED_ON_STARTUP:-false}"
export ENABLE_SCHEDULER="${ENABLE_SCHEDULER:-false}"

python -m compileall -q src tests alembic scripts
python -m ruff check src tests alembic scripts
pytest -q
alembic heads
alembic upgrade base:head --sql >/dev/null
alembic downgrade head:base --sql >/dev/null
