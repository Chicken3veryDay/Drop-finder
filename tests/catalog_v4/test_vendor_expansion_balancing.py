from __future__ import annotations

import unittest

from scripts import vendor_expansion


class Core:
    def __init__(self):
        self.SOURCES = [
            (source_id, source_id, [("html", f"https://{source_id}.example/", "storewide")])
            for source_id in (
                "hello_mary",
                "cali_canna",
                "five_leaf_wellness",
                "bay_smokes",
                "dr_ganja",
                "exhale_wellness",
                "wnc_cbd",
                "eight_horses_hemp",
                "green_unicorn_farms",
                "holy_city_farms",
                "hemp_hop",
                "veteran_grown_hemp",
                "small_a",
                "small_b",
                "small_c",
                "small_d",
                "small_e",
                "small_f",
            )
        ]


class Worker:
    def __init__(self):
        self.core = Core()
        self.FALLBACK_HTML_ROUTES = {}


class VendorExpansionBalancingTests(unittest.TestCase):
    def test_every_source_is_preserved_once_and_bins_are_capacity_bounded(self):
        worker = Worker()
        original = {source[0] for source in worker.core.SOURCES}
        bins = vendor_expansion.balance_sources(worker, shard_count=6)

        flattened = [source_id for bucket in bins for source_id in bucket]
        self.assertEqual(set(flattened), original)
        self.assertEqual(len(flattened), len(original))
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertLessEqual(max(map(len, bins)) - min(map(len, bins)), 1)

        modulo_bins = tuple(
            tuple(str(source[0]) for index, source in enumerate(worker.core.SOURCES) if index % 6 == shard)
            for shard in range(6)
        )
        self.assertEqual(modulo_bins, bins)

    def test_largest_known_sources_are_spread_across_distinct_shards(self):
        worker = Worker()
        bins = vendor_expansion.balance_sources(worker, shard_count=6)
        location = {
            source_id: shard
            for shard, bucket in enumerate(bins)
            for source_id in bucket
        }
        largest = ("hello_mary", "cali_canna", "five_leaf_wellness", "bay_smokes")
        self.assertEqual(len({location[source_id] for source_id in largest}), len(largest))

    def test_invalid_shard_count_fails_closed(self):
        with self.assertRaises(ValueError):
            vendor_expansion.balance_sources(Worker(), shard_count=0)


if __name__ == "__main__":
    unittest.main()
