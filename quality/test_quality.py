from __future__ import annotations

import unittest

import numpy as np

from evaluate import hamming, negative_histogram
from report import threshold_at


class QualityTest(unittest.TestCase):
    def test_hamming_spans_hash(self) -> None:
        self.assertEqual(hamming(bytes(16), bytes(16)), 0)
        self.assertEqual(hamming(bytes(16), bytes([255]) * 16), 128)

    def test_negative_histogram_counts_each_pair_once(self) -> None:
        hashes = np.asarray([[0], [1], [3]], dtype=np.uint8)
        histogram, exact = negative_histogram(hashes, block=2)
        self.assertEqual(histogram.sum(), 3)
        self.assertEqual(histogram[1], 2)
        self.assertEqual(histogram[2], 1)
        self.assertEqual(len(exact), 0)

    def test_threshold_respects_target_rate(self) -> None:
        histogram = np.asarray([1, 4, 5], dtype=np.int64)
        self.assertEqual(threshold_at(histogram, 0.5), (1, 0.5))
        self.assertEqual(threshold_at(histogram, 0.05), (-1, 0.0))


if __name__ == "__main__":
    unittest.main()
