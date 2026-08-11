#!/usr/bin/env python3
"""Run the AR Collections Dashboard with a /health endpoint for the ALB.

The ALB target group health-checks `GET /health`. Streamlit only ships
`/healthz` and `/_stcore/health`, so before starting the server we add a `/health`
route to its Tornado application. If that ever fails (e.g. Streamlit internals
change), we fall back to registering nothing and log loudly — `/healthz` still
answers, so the service can be re-pointed without a code change.

Runtime settings (PORT, NAME) come from APP_SECRETS, never from Dockerfile ENV.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import tornado.web

APP_SCRIPT = os.environ.get("APP_SCRIPT", "app.py")


def _app_secrets() -> dict:
    raw = os.environ.get("APP_SECRETS")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


_SECRETS = _app_secrets()


def _setting(key: str, default: str) -> str:
    value = _SECRETS.get(key) or os.environ.get(key) or ""
    return str(value) if str(value).strip() else default


SERVICE_NAME = _setting("NAME", "ar-collections-dashboard")


class HealthHandler(tornado.web.RequestHandler):
    """Liveness/readiness probe for the ALB target group."""

    def check_xsrf_cookie(self) -> None:  # probes send no XSRF token
        return

    def set_default_headers(self) -> None:
        self.set_header("Content-Type", "application/json")
        self.set_header("Cache-Control", "no-store")

    def get(self) -> None:
        self.write(
            json.dumps(
                {
                    "status": "healthy",
                    "service": SERVICE_NAME,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            )
        )

    def head(self) -> None:
        self.finish()


def _install_health_route() -> bool:
    """Add /health to Streamlit's Tornado app. Returns True on success."""
    try:
        from streamlit.web.server.server import Server

        original_create_app = Server._create_app

        def _create_app_with_health(self):  # type: ignore[no-untyped-def]
            app = original_create_app(self)
            # add_handlers prepends, so /health wins over Streamlit's catch-all.
            app.add_handlers(r".*", [(r"/health/?", HealthHandler)])
            return app

        Server._create_app = _create_app_with_health  # type: ignore[method-assign]
        return True
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[run_app] WARNING: could not register /health ({exc!r}). "
            "Streamlit's /healthz and /_stcore/health still respond; "
            "re-point the ALB health check if needed.",
            file=sys.stderr,
            flush=True,
        )
        return False


def main() -> int:
    port = _setting("PORT", "3000")
    if not port.isdigit():
        print(f"[run_app] FATAL: PORT '{port}' is not numeric.", file=sys.stderr)
        return 1

    installed = _install_health_route()
    print(
        f"[run_app] service={SERVICE_NAME} port={port} health={'/health' if installed else '/healthz'}",
        flush=True,
    )

    from streamlit.web import bootstrap

    flag_options = {
        "server.port": int(port),
        "server.address": "0.0.0.0",       # ALB reaches the task directly
        "server.headless": True,
        "server.fileWatcherType": "none",
        "browser.gatherUsageStats": False,
    }
    bootstrap.load_config_options(flag_options=flag_options)
    bootstrap.run(APP_SCRIPT, False, [], flag_options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
