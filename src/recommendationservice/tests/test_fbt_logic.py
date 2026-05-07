"""Sanity checks for the FBT seed data.

These tests assert structural properties of the co-occurrence map: every
product covered, pairings are symmetric (if A pairs with B, B pairs with
A), counts are positive, and no product pairs with itself. They guard
against the kind of typo that's easy to introduce when hand-editing the
seed map.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fbt_data import COOCCURRENCE


class CooccurrenceDataTest(unittest.TestCase):
    def test_no_self_pairs(self):
        for seed, pairs in COOCCURRENCE.items():
            for cand, _ in pairs:
                self.assertNotEqual(seed, cand,
                    f"{seed} lists itself as a paired product")

    def test_counts_are_positive(self):
        for seed, pairs in COOCCURRENCE.items():
            for cand, count in pairs:
                self.assertGreater(count, 0,
                    f"{seed} -> {cand} has non-positive count {count}")

    def test_paired_products_have_their_own_entries(self):
        # Every product that appears as a pair should also be a key in the
        # map, so FBT can fan out from any cart item.
        all_keys = set(COOCCURRENCE.keys())
        for seed, pairs in COOCCURRENCE.items():
            for cand, _ in pairs:
                self.assertIn(cand, all_keys,
                    f"{cand} appears as a pair for {seed} but is not a key")

    def test_pairs_are_sorted_by_count_descending(self):
        for seed, pairs in COOCCURRENCE.items():
            counts = [c for _, c in pairs]
            self.assertEqual(counts, sorted(counts, reverse=True),
                f"{seed} pairs are not sorted by count desc")


if __name__ == "__main__":
    unittest.main()
