"""Shared interface for listing sources."""

from __future__ import annotations

from typing import Protocol


class Source(Protocol):
    name: str
    enabled: bool

    def search(self, query: str, max_results: int) -> list[dict]:
        """Return listings in the standardized shape.

        Price fields should include item_price_cad, shipping_cad,
        total_price_cad, and shipping_is_estimated.
        """
        ...
