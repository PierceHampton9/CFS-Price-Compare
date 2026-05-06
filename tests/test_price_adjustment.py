import unittest

from pc_pricer.price_adjustment import apply_pricing_basis


class PriceAdjustmentTests(unittest.TestCase):
    def test_adds_conservative_range_for_asking_only_results(self):
        result = apply_pricing_basis(
            {
                "count": 2,
                "median_price_cad": 500,
                "sold_count": 0,
                "asking_count": 2,
            },
            asking_discount_low=0.05,
            asking_discount_high=0.10,
        )

        self.assertEqual(result["pricing_basis"], "asking_adjusted")
        self.assertEqual(result["asking_median_price_cad"], 500)
        self.assertEqual(result["conservative_low_cad"], 450)
        self.assertEqual(result["conservative_high_cad"], 475)

    def test_marks_sold_basis_when_sold_results_exist(self):
        result = apply_pricing_basis(
            {
                "count": 2,
                "median_price_cad": 400,
                "sold_count": 2,
                "asking_count": 0,
            }
        )

        self.assertEqual(result["pricing_basis"], "sold")
        self.assertNotIn("conservative_low_cad", result)

    def test_leaves_empty_results_without_basis(self):
        result = apply_pricing_basis({"count": 0, "sold_count": 0, "asking_count": 0})

        self.assertNotIn("pricing_basis", result)


if __name__ == "__main__":
    unittest.main()
