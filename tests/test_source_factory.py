import unittest

from pc_pricer.sources.factory import build_listing_sources


class SourceFactoryTests(unittest.TestCase):
    def test_builds_enabled_sources_from_config(self):
        sources = build_listing_sources(
            {
                "sources": {
                    "ebay": {"enabled": True, "marketplace": "EBAY_US"},
                    "refurb_io": {"enabled": True, "base_url": "https://example.test"},
                    "amazon_renewed": {"enabled": False},
                }
            },
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource, "amazon_renewed": FakeAmazonSource},
        )

        self.assertEqual([source.name for source in sources], ["ebay", "refurb_io"])
        self.assertEqual(sources[0].marketplace, "EBAY_US")
        self.assertEqual(sources[1].base_url, "https://example.test")

    def test_marketplace_override_applies_to_ebay(self):
        sources = build_listing_sources(
            {"sources": {"ebay": {"enabled": True, "marketplace": "EBAY_US"}, "refurb_io": {"enabled": False}}},
            marketplace_override="EBAY_CA",
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource, "amazon_renewed": FakeAmazonSource},
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].marketplace, "EBAY_CA")

    def test_amazon_renewed_is_disabled_by_default(self):
        sources = build_listing_sources(
            {"sources": {"ebay": {"enabled": False}, "refurb_io": {"enabled": False}}},
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource, "amazon_renewed": FakeAmazonSource},
        )

        self.assertEqual(sources, [])

    def test_builds_amazon_renewed_when_enabled(self):
        sources = build_listing_sources(
            {
                "sources": {
                    "ebay": {"enabled": False},
                    "refurb_io": {"enabled": False},
                    "amazon_renewed": {
                        "enabled": True,
                        "base_url": "https://www.amazon.ca",
                        "browser": "firefox",
                        "channel": "msedge",
                        "headless": False,
                        "timeout_ms": 9000,
                        "max_product_pages": 3,
                    },
                }
            },
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource, "amazon_renewed": FakeAmazonSource},
        )

        self.assertEqual([source.name for source in sources], ["amazon_renewed"])
        self.assertEqual(sources[0].base_url, "https://www.amazon.ca")
        self.assertEqual(sources[0].browser, "firefox")
        self.assertEqual(sources[0].channel, "msedge")
        self.assertIs(sources[0].headless, False)
        self.assertEqual(sources[0].timeout_ms, 9000)
        self.assertEqual(sources[0].max_product_pages, 3)

    def test_amazon_renewed_defaults_to_headless_when_enabled(self):
        sources = build_listing_sources(
            {
                "sources": {
                    "ebay": {"enabled": False},
                    "refurb_io": {"enabled": False},
                    "amazon_renewed": {"enabled": True},
                }
            },
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource, "amazon_renewed": FakeAmazonSource},
        )

        self.assertEqual([source.name for source in sources], ["amazon_renewed"])
        self.assertIs(sources[0].headless, True)
        self.assertEqual(sources[0].max_product_pages, 3)


class FakeEbaySource:
    name = "ebay"

    def __init__(self, marketplace):
        self.marketplace = marketplace


class FakeRefurbSource:
    name = "refurb_io"

    def __init__(self, base_url):
        self.base_url = base_url


class FakeAmazonSource:
    name = "amazon_renewed"

    def __init__(self, base_url, browser, channel, headless, timeout_ms, max_product_pages):
        self.base_url = base_url
        self.browser = browser
        self.channel = channel
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_product_pages = max_product_pages


if __name__ == "__main__":
    unittest.main()
