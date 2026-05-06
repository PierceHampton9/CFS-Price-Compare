"""Load simple project configuration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "default_condition": "good",
    "default_limit": 10,
    "default_limit_per_query": 10,
    "min_comparables": 5,
    "warn_below_comparables": 10,
    "wide_iqr_ratio": 0.40,
    "support_limit": 5,
    "max_sold_listing_age_days": 90,
    "max_asking_listing_age_days": 30,
    "sources": {
        "ebay": {
            "enabled": True,
            "marketplace": "EBAY_CA",
        },
        "canada_computers": {
            "enabled": False,
        },
    },
}


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load config.yaml, falling back to defaults when the file is absent."""
    config = deepcopy(DEFAULT_CONFIG)
    config_path = Path(path)
    if not config_path.exists():
        return config

    parsed = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    return _deep_merge(config, parsed)


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
