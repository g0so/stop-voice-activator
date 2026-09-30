from __future__ import annotations

import unittest

from protocol import AUDIO, HEADER, ProtocolError, encode_frame, recv_frame


class ProtocolTests(unittest.TestCase):
    class FakeSocket:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def recv(self, size: int) -> bytes:
            result, self.data = self.data[:size], self.data[size:]
            return result

    def test_round_trip(self) -> None:
        frame = recv_frame(self.FakeSocket(encode_frame(AUDIO, b"abc")))
        self.assertEqual(frame.frame_type, AUDIO)
        self.assertEqual(frame.payload, b"abc")

    def test_bad_magic(self) -> None:
        with self.assertRaises(ProtocolError):
            recv_frame(self.FakeSocket(HEADER.pack(b"NO", 1, AUDIO, 0)))


if __name__ == "__main__":
    unittest.main()
