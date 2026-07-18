import unittest

import scripts.multi_product as multi_product
from scripts.multi_product.classification import (
    CANNABIS_FLOWER,
    CANNABIS_VAPE,
    ENABLED_PRODUCT_TYPES,
    PSILOCYBIN_MUSHROOM,
    PSILOCYBIN_VAPE,
    SUPPORTED_PRODUCT_TYPES,
    classify_product,
)


class EdibleRetirementTests(unittest.TestCase):
    def test_supported_taxonomy_contains_only_production_types(self):
        expected = (
            CANNABIS_FLOWER,
            CANNABIS_VAPE,
            PSILOCYBIN_MUSHROOM,
            PSILOCYBIN_VAPE,
        )
        self.assertEqual(SUPPORTED_PRODUCT_TYPES, expected)
        self.assertEqual(ENABLED_PRODUCT_TYPES, expected)
        self.assertFalse(hasattr(multi_product, "CANNABIS_EDIBLE"))

    def test_edible_only_and_mixed_edible_offers_are_not_reclassified(self):
        self.assertIsNone(classify_product(name="Delta-9 THC Gummies 10mg 20 count"))
        self.assertIsNone(classify_product(name="THCA and magic mushroom gummy variety pack"))
        self.assertIsNone(classify_product(name="THCA chocolate edible 100mg"))


if __name__ == "__main__":
    unittest.main()
