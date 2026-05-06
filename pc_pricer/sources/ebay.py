"""eBay listing source."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib import error, parse, request


BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
OAUTH_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"


JsonHttpGet = Callable[[str, dict[str, str]], dict[str, Any]]
JsonHttpPost = Callable[[str, dict[str, str], dict[str, str]], dict[str, Any]]


@dataclass
class EbayCredentials:
    client_id: str | None = None
    client_secret: str | None = None

    @classmethod
    def from_env(
        cls,
        client_id_env: str = "EBAY_CLIENT_ID",
        client_secret_env: str = "EBAY_CLIENT_SECRET",
    ) -> "EbayCredentials":
        return cls(
            client_id=os.getenv(client_id_env),
            client_secret=os.getenv(client_secret_env),
        )

    def can_authenticate(self) -> bool:
        return bool(self.client_id and self.client_secret)


class EbaySource:
    name = "ebay"

    def __init__(
        self,
        enabled: bool = True,
        marketplace: str = "EBAY_CA",
        credentials: EbayCredentials | None = None,
        http_get: JsonHttpGet | None = None,
        http_post: JsonHttpPost | None = None,
    ) -> None:
        self.enabled = enabled
        self.marketplace = marketplace
        self.credentials = credentials or EbayCredentials.from_env()
        self._http_get = http_get or _http_get_json
        self._http_post = http_post or _http_post_json
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    def search(self, query: str, max_results: int) -> list[dict]:
        """Search active eBay listings for the configured marketplace."""
        if not self.enabled:
            return []
        if not self.credentials.can_authenticate():
            raise RuntimeError(
                "Missing eBay credentials. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET."
            )

        params = {
            "q": query,
            "limit": str(max_results),
            "fieldgroups": "EXTENDED",
        }
        url = f"{BROWSE_SEARCH_URL}?{parse.urlencode(params)}"
        payload = self._http_get(url, self._headers())

        listings = []
        for item in payload.get("itemSummaries") or []:
            listing = _listing_from_browse_item(item)
            if listing:
                listings.append(listing)
        return listings

    def check_credentials(self) -> dict[str, str]:
        """Check whether eBay credentials are available for API use."""
        if not self.credentials.can_authenticate():
            raise RuntimeError(
                "Missing eBay credentials. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET."
            )

        self._access_token()
        return {
            "status": "oauth_token_minted",
            "message": "OAuth token request succeeded.",
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            "Accept": "application/json",
        }

    def _access_token(self) -> str:
        if self._token and not self._token_is_expired():
            return self._token

        if not self.credentials.client_id or not self.credentials.client_secret:
            raise RuntimeError("Missing eBay client ID/client secret for OAuth token request.")

        basic_auth = base64.b64encode(
            f"{self.credentials.client_id}:{self.credentials.client_secret}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        body = {
            "grant_type": "client_credentials",
            "scope": OAUTH_SCOPE,
        }
        payload = self._http_post(OAUTH_TOKEN_URL, headers, body)
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("eBay OAuth response did not include an access token.")

        expires_in = _safe_int(payload.get("expires_in")) or 7200
        self._token = str(token)
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        return self._token

    def _token_is_expired(self) -> bool:
        if not self._token_expires_at:
            return False
        return datetime.now(timezone.utc) >= self._token_expires_at


def _listing_from_browse_item(item: dict[str, Any]) -> dict[str, Any] | None:
    item_price = _money_to_cad(item.get("price"))
    if item_price is None:
        return None

    shipping = _shipping_to_cad(item.get("shippingOptions"))
    shipping_is_estimated = shipping is None
    total_price = item_price + (shipping or 0.0)

    return {
        "source": "ebay",
        "item_id": _clean(item.get("itemId")),
        "title": _clean(item.get("title")) or "",
        "item_price_cad": item_price,
        "shipping_cad": shipping,
        "total_price_cad": round(total_price, 2),
        "shipping_is_estimated": shipping_is_estimated,
        "condition_raw": _clean(item.get("condition")),
        "condition_norm": None,
        "url": _clean(item.get("itemWebUrl")) or "",
        "location": _location(item.get("itemLocation")),
        "listing_date": _date_from_ebay_timestamp(item.get("itemCreationDate")),
        "is_sold": False,
        "query_tier": None,
    }


def _money_to_cad(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    if value.get("currency") != "CAD":
        return None
    amount = value.get("value")
    if amount is None:
        return None
    try:
        return round(float(amount), 2)
    except (TypeError, ValueError):
        return None


def _shipping_to_cad(shipping_options: Any) -> float | None:
    if not isinstance(shipping_options, list):
        return None

    costs = [
        _money_to_cad(option.get("shippingCost"))
        for option in shipping_options
        if isinstance(option, dict)
    ]
    costs = [cost for cost in costs if cost is not None]
    if not costs:
        return None
    return min(costs)


def _location(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    parts = [
        _clean(value.get("city")),
        _clean(value.get("stateOrProvince")),
        _clean(value.get("country")),
    ]
    parts = [part for part in parts if part]
    return ", ".join(parts) or None


def _date_from_ebay_timestamp(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _http_get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"eBay request failed with HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"eBay request failed: {exc.reason}") from exc


def _http_post_json(url: str, headers: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
    encoded_body = parse.urlencode(body).encode("utf-8")
    req = request.Request(url, data=encoded_body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"eBay request failed with HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"eBay request failed: {exc.reason}") from exc


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
