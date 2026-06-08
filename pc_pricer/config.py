"""Load simple project configuration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "default_condition": "good",
    "default_limit": 10,
    "default_limit_per_query": 10,
    "min_comparables": 5,
    "warn_below_comparables": 10,
    "wide_iqr_ratio": 0.40,
    "support_limit": 5,
    "high_shipping_cad": 75,
    "high_shipping_ratio": 0.25,
    "asking_discount_low": 0.00,
    "asking_discount_high": 0.05,
    "max_sold_listing_age_days": 90,
    "max_asking_listing_age_days": 30,
    "manufacturer_lookup": {
        "enabled": False,
        "timeout_seconds": 5,
        "max_pages": 2,
    },
    "sources": {
        "ebay": {
            "enabled": True,
            "marketplace": "EBAY_CA",
        },
        "refurb_io": {
            "enabled": True,
            "base_url": "https://ca.refurb.io",
        },
        "amazon_renewed": {
            "enabled": False,
            "base_url": "https://www.amazon.ca",
            "browser": "chromium",
            "channel": "msedge",
            "headless": True,
            "timeout_ms": 15000,
            "max_product_pages": 5,
        },
        "canada_computers": {
            "enabled": False,
        },
    },
}


def default_config_path() -> Path:
    """Return config.yaml beside the exe when packaged, otherwise in the working directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.yaml"
    return Path.cwd() / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml, falling back to defaults when the file is absent."""
    config = deepcopy(DEFAULT_CONFIG)
    config_path = Path(path) if path is not None else default_config_path()
    if not config_path.exists():
        return config

    parsed = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    return _deep_merge(config, parsed)


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    """Write config using the simple YAML subset this project reads."""
    Path(path).write_text(_format_simple_yaml(config), encoding="utf-8")


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            raise RuntimeError(f"Config line {line_number} uses tabs; use spaces.")

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2:
            raise RuntimeError(f"Config line {line_number} has unsupported indentation.")

        line = _strip_inline_comment(raw_line.strip())
        if not line:
            continue
        if ":" not in line:
            raise RuntimeError(f"Config line {line_number} is missing ':'.")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            raise RuntimeError(f"Config line {line_number} has an empty key.")

        while indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if raw_value:
            parent[key] = _parse_scalar(raw_value)
        else:
            section: dict[str, Any] = {}
            parent[key] = section
            stack.append((indent, section))

    return root


def _strip_inline_comment(value: str) -> str:
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(value):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            return value[:index].rstrip()

    return value


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _format_simple_yaml(config: dict[str, Any]) -> str:
    lines = []
    _append_yaml_lines(lines, config, 0)
    return "\n".join(lines) + "\n"


def _append_yaml_lines(lines: list[str], values: dict[str, Any], indent: int) -> None:
    prefix = " " * indent
    for key, value in values.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            _append_yaml_lines(lines, value, indent + 2)
        else:
            lines.append(f"{prefix}{key}: {_format_scalar(value)}")


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or text.strip() != text or any(char in text for char in [":", "#", "\n"]):
        return repr(text)
    return text
