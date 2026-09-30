#!/usr/bin/env python3
"""Send a mono 16 kHz PCM16 WAV through the ESP32 framing protocol."""

from __future__ import annotations

import argparse
import socket
import struct
import time
import wave
from pathlib import Path

from adpcm import CODEC_IMA_ADPCM, CODEC_PCM16, encode_ima_adpcm
from protocol import (
    AUDIO,
    AUDIO_PREFIX,
    END,
    END_STRUCT,
    HELLO,
    HELLO_STRUCT,
    TRIGGER,
    TRIGGER_STRUCT,
    encode_frame,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--codec", choices=("adpcm", "pcm"), default="adpcm")
    args = parser.parse_args()

    with wave.open(str(args.wav), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (16000, 1, 2):
            raise SystemExit("WAV must be mono 16 kHz PCM16")
        pcm = source.readframes(source.getnframes())

    activation_id = 1
    trigger_ms = int(time.monotonic() * 1000) & 0xFFFFFFFF
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.sendall(encode_frame(HELLO, HELLO_STRUCT.pack(16000, 16, 1, 14, 160, 0)))
        sock.sendall(encode_frame(TRIGGER, TRIGGER_STRUCT.pack(activation_id, trigger_ms, 30000, 0, len(pcm) // 32, 0)))
        predictor, step_index = 0, 0
        for sequence, offset in enumerate(range(0, len(pcm), 320)):
            block = pcm[offset : offset + 320]
            send_ms = int(time.monotonic() * 1000) & 0xFFFFFFFF
            sample_count = len(block) // 2
            frame_predictor, frame_index = predictor, step_index
            if args.codec == "adpcm":
                samples = struct.unpack(f"<{sample_count}h", block)
                encoded, predictor, step_index = encode_ima_adpcm(samples, predictor, step_index)
                codec = CODEC_IMA_ADPCM
            else:
                encoded = block
                codec = CODEC_PCM16
            prefix = AUDIO_PREFIX.pack(
                activation_id, sequence, offset // 2, send_ms,
                frame_predictor, frame_index, codec, sample_count,
            )
            sock.sendall(encode_frame(AUDIO, prefix + encoded))
            if args.realtime:
                time.sleep(len(block) / 2 / 16000)
        first_send_ms = trigger_ms
        samples = len(pcm) // 2
        sock.sendall(encode_frame(END, END_STRUCT.pack(activation_id, samples, 0, trigger_ms, first_send_ms)))


if __name__ == "__main__":
    main()
