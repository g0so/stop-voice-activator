#!/usr/bin/env python3
"""Save a five-second capture from mic_recorder.ino. Requires pyserial."""
import argparse
from array import array
from pathlib import Path
import math
import sys
import time
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="ESP32 serial port, e.g. /dev/ttyUSB0")
    parser.add_argument("--output", type=Path, default=Path("mic_test.wav"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"{args.output} already exists; choose a new --output name")
    try:
        import serial
    except ImportError:
        parser.exit(1, "Missing pyserial. Install it in your Python virtual environment.\n")

    with serial.Serial(args.port, 921600, timeout=1) as device:
        time.sleep(2)  # USB serial adapters may reset the ESP32 on opening.
        device.reset_input_buffer()
        input("Press Enter when ready, then speak for five seconds: ")
        device.write(b"r")
        deadline = time.monotonic() + 8
        while True:
            line = device.readline().strip()
            if line == b"AUDIO 16000 160000":
                break
            if line.startswith(b"ERROR"):
                raise RuntimeError(line.decode(errors="replace"))
            if time.monotonic() > deadline:
                raise RuntimeError("No recording header. Check the sketch and close Serial Monitor.")
        print("Recording now: speak your chosen test word or sentence.", flush=True)
        audio = bytearray()
        deadline = time.monotonic() + 12
        while len(audio) < 160000 and time.monotonic() < deadline:
            audio.extend(device.read(min(4096, 160000 - len(audio))))
        if len(audio) != 160000:
            raise RuntimeError(f"Incomplete recording: {len(audio)} of 160000 bytes received")
        if device.readline().strip() != b"DONE":
            raise RuntimeError("Missing completion marker; recording may be corrupted")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(audio)
    samples = array("h", audio)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(v) for v in samples)
    rms = math.sqrt(sum(v * v for v in samples) / len(samples))
    clipped = sum(v >= 32767 or v <= -32768 for v in samples)
    print(f"Saved: {args.output.resolve()}")
    print(f"Duration: 5.00 s | Peak: {peak}/32768 | RMS: {rms:.1f} | Clipped samples: {clipped}")
    print("Listen for clear speech, correct speed, clicks, and distortion.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Recording failed: {error}", file=sys.stderr)
        sys.exit(1)
