import unittest

from pc_pricer.source_status import merge_config_source_statuses


class SourceStatusTests(unittest.TestCase):
    def test_summarizes_dropped_candidate_reasons(self):
        statuses = merge_config_source_statuses(
            [
                {
                    "source": "amazon_renewed",
                    "enabled": True,
                    "searched": True,
                    "query_count": 1,
                    "queries": ["ThinkPad Renewed"],
                    "raw_listing_count": 0,
                    "candidate_count": 2,
                    "dropped_candidate_count": 2,
                    "dropped_candidate_reasons": {"missing_price": 1, "missing_renewed_condition": 1},
                    "error_count": 0,
                    "errors": [],
                }
            ],
            {
                "sources": {
                    "ebay": {"enabled": False},
                    "refurb_io": {"enabled": False},
                    "amazon_renewed": {"enabled": True},
                }
            },
        )

        amazon = next(status for status in statuses if status["source"] == "amazon_renewed")

        self.assertEqual(amazon["status"], "no_results")
        self.assertIn("2 candidate(s) dropped", amazon["message"])
        self.assertIn("missing_price=1", amazon["message"])
        self.assertIn("missing_renewed_condition=1", amazon["message"])


if __name__ == "__main__":
    unittest.main()
