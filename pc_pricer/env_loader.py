"""Load local environment variables for CLI use."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_env_path() -> Path:
    """Return the local .env path for source runs or packaged exe runs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ".env"
    return Path.cwd() / ".env"


def load_env_file(path: str | Path | None = None, override: bool = False) -> None:
    """Load KEY=VALUE pairs from a local .env file.

    By default, existing shell variables win. Pass override=True when the saved
    .env file should replace values already present in the current process.
    """
    env_path = Path(path) if path is not None else default_env_path()
    _load_one_env_file(env_path, override=override)


def _load_one_env_file(env_path: Path, override: bool = False) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if not parsed:
            continue

        key, value = parsed
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    return key, _clean_value(value)


def _clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
