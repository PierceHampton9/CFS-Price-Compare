"""Build configured listing sources."""

from __future__ import annotations

from typing import Any, Callable

from pc_pricer.sources.ebay import EbaySource
from pc_pricer.sources.refurb_io import RefurbIoSource


SourceClass = Callable[..., Any]


def build_listing_sources(
    config: dict[str, Any],
    marketplace_override: str | None = None,
    source_classes: dict[str, SourceClass] | None = None,
) -> list[Any]:
    """Return enabled sources from config in deterministic priority order."""
    classes = {
        "ebay": EbaySource,
        "refurb_io": RefurbIoSource,
        **(source_classes or {}),
    }

    sources = []
    ebay_config = _source_config(config, "ebay")
    if _bool_value(ebay_config.get("enabled"), True):
        marketplace = marketplace_override or str(ebay_config.get("marketplace") or "EBAY_CA")
        sources.append(classes["ebay"](marketplace=marketplace))

    refurb_config = _source_config(config, "refurb_io")
    if _bool_value(refurb_config.get("enabled"), True):
        base_url = str(refurb_config.get("base_url") or "https://ca.refurb.io")
        sources.append(classes["refurb_io"](base_url=base_url))

    return sources


def _source_config(config: dict[str, Any], source_name: str) -> dict[str, Any]:
    sources = config.get("sources")
    if not isinstance(sources, dict):
        return {}
    source = sources.get(source_name)
    if not isinstance(source, dict):
        return {}
    return source


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
