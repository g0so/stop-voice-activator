from __future__ import annotations

import math
import unittest

from adpcm import decode_ima_adpcm, encode_ima_adpcm


class AdpcmTests(unittest.TestCase):
    def test_round_trip_length_and_error(self) -> None:
        samples = [int(12000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(160)]
        encoded, _, _ = encode_ima_adpcm(samples)
        decoded_bytes = decode_ima_adpcm(encoded, 0, 0, len(samples))
        self.assertEqual(len(encoded), 80)
        self.assertEqual(len(decoded_bytes), 320)
        decoded = [int.from_bytes(decoded_bytes[i:i + 2], "little", signed=True) for i in range(0, 320, 2)]
        mean_absolute_error = sum(abs(a - b) for a, b in zip(samples, decoded)) / len(samples)
        self.assertLess(mean_absolute_error, 1500)

    def test_odd_sample_count(self) -> None:
        encoded, _, _ = encode_ima_adpcm([100, -100, 200])
        self.assertEqual(len(encoded), 2)
        self.assertEqual(len(decode_ima_adpcm(encoded, 0, 0, 3)), 6)


if __name__ == "__main__":
    unittest.main()
