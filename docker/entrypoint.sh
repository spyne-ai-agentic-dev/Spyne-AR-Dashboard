#!/usr/bin/env bash
# Container entrypoint.
#   1. Materialise APP_SECRETS (Secrets Manager) into a Streamlit secrets file.
#   2. Exec the app, which listens on 0.0.0.0:$PORT and serves /health for the ALB.
# Single process, so ECS signals reach the app directly (exec, no wrapper).
set -euo pipefail

cd "${APP_DIR:-/app}"

python3 docker/bootstrap.py

exec python3 docker/run_app.py
