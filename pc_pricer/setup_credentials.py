"""Interactive setup for local eBay credentials."""

from __future__ import annotations

from getpass import getpass
from pathlib import Path
from typing import Callable

from pc_pricer.env_loader import default_env_path


InputFunc = Callable[[str], str]
SecretInputFunc = Callable[[str], str]


def run_setup(
    env_path: str | Path | None = None,
    input_func: InputFunc = input,
    secret_input_func: SecretInputFunc = getpass,
) -> Path:
    """Prompt for eBay credentials and write them to the local .env file."""
    target_path = Path(env_path) if env_path is not None else default_env_path()

    client_id = _prompt_required(input_func, "eBay Client ID / App ID: ")
    client_secret = _prompt_required(secret_input_func, "eBay Client Secret / Cert ID: ")

    write_credentials_env(target_path, client_id, client_secret)
    return target_path


def write_credentials_env(path: str | Path, client_id: str, client_secret: str) -> Path:
    """Create or update the local .env file with eBay credentials."""
    env_path = Path(path)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    values = _read_env_values(env_path)
    values["EBAY_CLIENT_ID"] = client_id.strip()
    values["EBAY_CLIENT_SECRET"] = client_secret.strip()

    lines = [
        "# Local eBay API credentials. Do not commit this file.",
        f"EBAY_CLIENT_ID={_quote_env_value(values['EBAY_CLIENT_ID'])}",
        f"EBAY_CLIENT_SECRET={_quote_env_value(values['EBAY_CLIENT_SECRET'])}",
    ]
    for key, value in values.items():
        if key in {"EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"}:
            continue
        lines.append(f"{key}={_quote_env_value(value)}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def _prompt_required(input_func: InputFunc, prompt: str) -> str:
    value = input_func(prompt).strip()
    if not value:
        raise RuntimeError("Setup cancelled because a required value was blank.")
    return value


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _clean_env_value(value)
    return values


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
