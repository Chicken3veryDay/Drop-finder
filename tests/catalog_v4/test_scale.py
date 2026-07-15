from __future__ import annotations

import unittest

from scripts.catalog_v4.benchmark import run


class ScaleContractTests(unittest.TestCase):
    def test_compact_index_and_deterministic_shards_scale(self) -> None:
        result = run(product_count=300, variants_per_product=4, detail_shards=16)
        self.assertEqual(result["input_rows"], 1200)
        self.assertEqual(result["products"], 300)
        self.assertEqual(result["variants"], 1200)
        self.assertEqual(result["rejections"], 0)
        self.assertGreater(result["detail_bytes"], result["index_bytes"])
        self.assertLess(result["largest_detail_shard_bytes"], result["detail_bytes"])


if __name__ == "__main__":
    unittest.main()
