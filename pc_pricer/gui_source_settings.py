"""GUI helpers for persisted pricing source preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pc_pricer.config import default_config_path, load_config, save_config


SOURCE_KEYS = ("ebay", "refurb_io", "amazon_renewed")


def load_source_settings(path: str | Path | None = None) -> dict[str, bool]:
    """Return enabled flags for GUI pricing sources."""
    config = load_config(path)
    return {source: _source_enabled(config, source) for source in SOURCE_KEYS}


def save_source_settings(settings: dict[str, bool], path: str | Path | None = None) -> dict[str, bool]:
    """Persist GUI pricing source toggles to config.yaml."""
    config_path = Path(path) if path is not None else default_config_path()
    config = load_config(config_path)
    sources = config.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        config["sources"] = sources

    saved = {}
    for source in SOURCE_KEYS:
        source_config = sources.setdefault(source, {})
        if not isinstance(source_config, dict):
            source_config = {}
            sources[source] = source_config
        current = _source_enabled(config, source)
        enabled = bool(settings.get(source, current))
        source_config["enabled"] = enabled
        saved[source] = enabled

    amazon_config = sources.setdefault("amazon_renewed", {})
    if isinstance(amazon_config, dict):
        amazon_config.setdefault("base_url", "https://www.amazon.ca")
        amazon_config.setdefault("browser", "chromium")
        amazon_config.setdefault("channel", "msedge")
        amazon_config.setdefault("headless", True)
        amazon_config.setdefault("timeout_ms", 15000)
        amazon_config.setdefault("max_product_pages", 1)

    save_config(config_path, config)
    return saved


def _source_enabled(config: dict[str, Any], source: str) -> bool:
    sources = config.get("sources")
    source_config = sources.get(source) if isinstance(sources, dict) else None
    if not isinstance(source_config, dict):
        return source != "amazon_renewed"
    default = source != "amazon_renewed"
    return _bool_value(source_config.get("enabled"), default)


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return default
