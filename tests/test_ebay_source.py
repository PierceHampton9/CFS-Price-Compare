import io
import unittest
import warnings
from datetime import date
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pc_pricer.sources import ebay
from pc_pricer.sources.ebay import EbayCredentials, EbaySource


class EbaySourceTests(unittest.TestCase):
    def test_credentials_load_from_environment(self):
        with patch.dict(
            "os.environ",
            {
                "EBAY_CLIENT_ID": "client-id",
                "EBAY_CLIENT_SECRET": "client-secret",
                "EBAY_ACCESS_TOKEN": "token",
            },
        ):
            credentials = EbayCredentials.from_env()

        self.assertEqual(credentials.client_id, "client-id")
        self.assertEqual(credentials.client_secret, "client-secret")
        self.assertEqual(credentials.access_token, "token")

    def test_search_maps_browse_items_to_standard_listings(self):
        seen = {}

        def fake_get(url, headers):
            seen["url"] = url
            seen["headers"] = headers
            return {
                "itemSummaries": [
                    {
                        "title": "Lenovo ThinkPad X13 Yoga Gen 2",
                        "price": {"value": "300.00", "currency": "CAD"},
                        "shippingOptions": [
                            {
                                "shippingCostType": "FIXED",
                                "shippingCost": {"value": "25.00", "currency": "CAD"},
                            }
                        ],
                        "condition": "Used",
                        "itemWebUrl": "https://www.ebay.ca/itm/example",
                        "itemLocation": {
                            "city": "Calgary",
                            "stateOrProvince": "AB",
                            "country": "CA",
                        },
                        "itemCreationDate": "2026-01-15T12:30:00.000Z",
                    }
                ]
            }

        source = EbaySource(
            credentials=EbayCredentials(access_token="test-token"),
            http_get=fake_get,
        )

        listings = source.search("ThinkPad X13 Yoga", max_results=5)

        self.assertIn("q=ThinkPad+X13+Yoga", seen["url"])
        self.assertEqual(seen["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(seen["headers"]["X-EBAY-C-MARKETPLACE-ID"], "EBAY_CA")
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["source"], "ebay")
        self.assertEqual(listings[0]["item_price_cad"], 300.00)
        self.assertEqual(listings[0]["shipping_cad"], 25.00)
        self.assertEqual(listings[0]["total_price_cad"], 325.00)
        self.assertFalse(listings[0]["shipping_is_estimated"])
        self.assertEqual(listings[0]["condition_raw"], "Used")
        self.assertEqual(listings[0]["location"], "Calgary, AB, CA")
        self.assertEqual(listings[0]["listing_date"], date(2026, 1, 15))
        self.assertFalse(listings[0]["is_sold"])

    def test_missing_shipping_is_flagged_as_estimated(self):
        def fake_get(_url, _headers):
            return {
                "itemSummaries": [
                    {
                        "title": "Dell OptiPlex",
                        "price": {"value": "180.00", "currency": "CAD"},
                        "condition": "Used",
                    }
                ]
            }

        source = EbaySource(
            credentials=EbayCredentials(access_token="test-token"),
            http_get=fake_get,
        )

        listing = source.search("Dell OptiPlex", max_results=1)[0]

        self.assertIsNone(listing["shipping_cad"])
        self.assertEqual(listing["total_price_cad"], 180.00)
        self.assertTrue(listing["shipping_is_estimated"])

    def test_non_cad_items_are_skipped_for_now(self):
        def fake_get(_url, _headers):
            return {
                "itemSummaries": [
                    {
                        "title": "US listing",
                        "price": {"value": "200.00", "currency": "USD"},
                    }
                ]
            }

        source = EbaySource(
            credentials=EbayCredentials(access_token="test-token"),
            http_get=fake_get,
        )

        self.assertEqual(source.search("laptop", max_results=1), [])

    def test_client_credentials_request_is_used_when_no_token_is_provided(self):
        posted = {}

        def fake_post(url, headers, body):
            posted["url"] = url
            posted["headers"] = headers
            posted["body"] = body
            return {"access_token": "minted-token", "expires_in": 7200}

        def fake_get(_url, headers):
            self.assertEqual(headers["Authorization"], "Bearer minted-token")
            return {"itemSummaries": []}

        source = EbaySource(
            credentials=EbayCredentials(client_id="client", client_secret="secret"),
            http_get=fake_get,
            http_post=fake_post,
        )

        source.search("laptop", max_results=1)

        self.assertIn("/identity/v1/oauth2/token", posted["url"])
        self.assertEqual(posted["body"]["grant_type"], "client_credentials")

    def test_check_credentials_uses_oauth_without_searching(self):
        called = {"get": False, "post": False}

        def fake_post(_url, _headers, _body):
            called["post"] = True
            return {"access_token": "minted-token", "expires_in": 7200}

        def fake_get(_url, _headers):
            called["get"] = True
            return {"itemSummaries": []}

        source = EbaySource(
            credentials=EbayCredentials(client_id="client", client_secret="secret"),
            http_get=fake_get,
            http_post=fake_post,
        )

        result = source.check_credentials()

        self.assertTrue(called["post"])
        self.assertFalse(called["get"])
        self.assertEqual(result["status"], "oauth_token_minted")

    def test_check_credentials_reports_existing_access_token_without_network(self):
        called = {"get": False, "post": False}

        def fake_post(_url, _headers, _body):
            called["post"] = True
            return {"access_token": "minted-token", "expires_in": 7200}

        def fake_get(_url, _headers):
            called["get"] = True
            return {"itemSummaries": []}

        source = EbaySource(
            credentials=EbayCredentials(access_token="existing-token"),
            http_get=fake_get,
            http_post=fake_post,
        )

        result = source.check_credentials()

        self.assertFalse(called["post"])
        self.assertFalse(called["get"])
        self.assertEqual(result["status"], "token_present")

    def test_missing_credentials_raise_clear_error(self):
        source = EbaySource(credentials=EbayCredentials())

        with self.assertRaisesRegex(RuntimeError, "Missing eBay credentials"):
            source.search("laptop", max_results=1)

    def test_check_credentials_raises_clear_error_when_missing_credentials(self):
        source = EbaySource(credentials=EbayCredentials())

        with self.assertRaisesRegex(RuntimeError, "Missing eBay credentials"):
            source.check_credentials()

    def test_http_errors_are_wrapped(self):
        def fake_urlopen(_req, timeout):
            self.assertEqual(timeout, 30)
            raise HTTPError(
                url="https://api.ebay.com/example",
                code=401,
                msg="Unauthorized",
                hdrs=Message(),
                fp=io.BytesIO(b""),
            )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            with patch("pc_pricer.sources.ebay.request.urlopen", fake_urlopen):
                with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                    ebay._http_get_json("https://api.ebay.com/example", {})

    def test_url_errors_are_wrapped(self):
        def fake_urlopen(_req, timeout):
            self.assertEqual(timeout, 30)
            raise URLError("network unavailable")

        with patch("pc_pricer.sources.ebay.request.urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "network unavailable"):
                ebay._http_get_json("https://api.ebay.com/example", {})


if __name__ == "__main__":
    unittest.main()
