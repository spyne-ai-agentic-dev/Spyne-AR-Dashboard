#!/usr/bin/env bash
# Container entrypoint: materialise secrets, render nginx config, then run
# Streamlit (internal) behind nginx (public). Exits if either process dies.
set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
cd "$APP_DIR"

# ── 1. APP_SECRETS → .streamlit/secrets.toml (fails fast if misconfigured) ────
python3 /app/docker/bootstrap.py

# ── 2. Runtime settings come from APP_SECRETS, never from Dockerfile ENV ──────
read_secret() {
  python3 - "$1" "$2" <<'PY'
import json, os, sys
key, default = sys.argv[1], sys.argv[2]
raw = os.environ.get("APP_SECRETS")
value = ""
if raw:
    try:
        value = str(json.loads(raw).get(key, "") or "")
    except Exception:
        value = ""
print(value or os.environ.get(key, "") or default)
PY
}

export PORT="$(read_secret PORT 3000)"
export SERVICE_NAME="$(read_secret NAME ar-collections-dashboard)"

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "[entrypoint] FATAL: PORT '$PORT' is not numeric." >&2
  exit 1
fi

echo "[entrypoint] service=$SERVICE_NAME port=$PORT" >&2

# ── 3. Render nginx config (only our two vars; leave nginx's $vars intact) ────
envsubst '${PORT} ${SERVICE_NAME}' \
  < /app/docker/nginx.conf.template \
  > /tmp/nginx.conf

# ── 4. Start Streamlit on loopback; nginx is the only public listener ─────────
streamlit run app.py \
  --server.port=8501 \
  --server.address=127.0.0.1 \
  --server.headless=true \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false &
STREAMLIT_PID=$!

nginx -c /tmp/nginx.conf -g 'daemon off;' &
NGINX_PID=$!

shutdown() {
  echo "[entrypoint] shutting down" >&2
  kill "$STREAMLIT_PID" "$NGINX_PID" 2>/dev/null || true
  wait "$STREAMLIT_PID" "$NGINX_PID" 2>/dev/null || true
}
trap shutdown TERM INT

# If either process exits, stop the container so ECS replaces the task.
wait -n "$STREAMLIT_PID" "$NGINX_PID"
EXIT_CODE=$?
echo "[entrypoint] a process exited (code $EXIT_CODE); stopping container" >&2
shutdown
exit "$EXIT_CODE"
