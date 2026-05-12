import unittest

from pc_pricer.sources.factory import build_listing_sources


class SourceFactoryTests(unittest.TestCase):
    def test_builds_enabled_sources_from_config(self):
        sources = build_listing_sources(
            {
                "sources": {
                    "ebay": {"enabled": True, "marketplace": "EBAY_US"},
                    "refurb_io": {"enabled": True, "base_url": "https://example.test"},
                }
            },
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource},
        )

        self.assertEqual([source.name for source in sources], ["ebay", "refurb_io"])
        self.assertEqual(sources[0].marketplace, "EBAY_US")
        self.assertEqual(sources[1].base_url, "https://example.test")

    def test_marketplace_override_applies_to_ebay(self):
        sources = build_listing_sources(
            {"sources": {"ebay": {"enabled": True, "marketplace": "EBAY_US"}, "refurb_io": {"enabled": False}}},
            marketplace_override="EBAY_CA",
            source_classes={"ebay": FakeEbaySource, "refurb_io": FakeRefurbSource},
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].marketplace, "EBAY_CA")


class FakeEbaySource:
    name = "ebay"

    def __init__(self, marketplace):
        self.marketplace = marketplace


class FakeRefurbSource:
    name = "refurb_io"

    def __init__(self, base_url):
        self.base_url = base_url


if __name__ == "__main__":
    unittest.main()
