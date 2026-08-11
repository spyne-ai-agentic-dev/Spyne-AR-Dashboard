#!/usr/bin/env python3
"""Translate the ECS-injected APP_SECRETS blob into a Streamlit secrets file.

The platform team injects ONE environment variable, APP_SECRETS, holding a JSON
document from AWS Secrets Manager. The dashboard reads its configuration through
`st.secrets`, so at container start we materialise APP_SECRETS into
`.streamlit/secrets.toml`. Nothing is baked into the image; the file only ever
exists inside the running container.

Fails fast (non-zero exit) when required configuration is missing, per CLAUDE.md.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Nested objects become [sections] in secrets.toml. Top-level scalars (NAME,
# PORT, ALLOWED_ORIGIN, NODE_ENV) are runtime settings, not app secrets.
_RUNTIME_KEYS = {"NAME", "PORT", "ALLOWED_ORIGIN", "NODE_ENV"}

# Without Google OAuth config nobody can sign in, so treat it as mandatory.
_REQUIRED_SECTIONS = ("google_oauth",)

SECRETS_PATH = Path(os.environ.get("STREAMLIT_SECRETS_PATH", "/app/.streamlit/secrets.toml"))


def _toml_escape(value: str) -> str:
    """Escape a Python string for a TOML basic string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return f'"{_toml_escape(str(value))}"'


def _render_toml(payload: dict) -> str:
    """Serialise {scalars + one level of nested objects} into TOML."""
    lines: list[str] = ["# Generated from APP_SECRETS at container start. Do not edit."]

    for key, value in payload.items():
        if isinstance(value, dict) or key in _RUNTIME_KEYS:
            continue
        lines.append(f"{key} = {_toml_value(value)}")

    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        lines.append("")
        lines.append(f"[{key}]")
        for sub_key, sub_value in value.items():
            if isinstance(sub_value, dict):
                # Two-level nesting is not used by this app; skip rather than
                # emit invalid TOML.
                continue
            lines.append(f'"{_toml_escape(str(sub_key))}" = {_toml_value(sub_value)}')

    return "\n".join(lines) + "\n"


def main() -> int:
    raw = os.environ.get("APP_SECRETS")
    if not raw:
        # Local development: rely on a developer-supplied secrets.toml instead.
        if SECRETS_PATH.exists():
            print(f"[bootstrap] APP_SECRETS not set; using existing {SECRETS_PATH}", flush=True)
            return 0
        print(
            "[bootstrap] FATAL: APP_SECRETS is not set and no secrets file exists at "
            f"{SECRETS_PATH}. The platform team must attach the Secrets Manager secret.",
            file=sys.stderr,
        )
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[bootstrap] FATAL: APP_SECRETS is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        print("[bootstrap] FATAL: APP_SECRETS must be a JSON object.", file=sys.stderr)
        return 1

    missing = [s for s in _REQUIRED_SECTIONS if not isinstance(payload.get(s), dict)]
    if missing:
        print(
            f"[bootstrap] FATAL: APP_SECRETS is missing required section(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(_render_toml(payload))
    SECRETS_PATH.chmod(0o600)

    sections = sorted(k for k, v in payload.items() if isinstance(v, dict))
    print(f"[bootstrap] Wrote {SECRETS_PATH} with sections: {', '.join(sections) or '(none)'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
