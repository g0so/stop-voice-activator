#!/usr/bin/env python3
"""Guided five-second recordings using the existing mic_recorder sketch."""
import argparse
from array import array
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parent / "dataset" / "raw"
OTHER_WORDS = ["pocket", "socket", "rock", "lock it", "ticket", "market",
               "robot", "racket", "stop", "hello", "turn on the light",
               "open the door", "what time is it", "please come here", "good morning"]


def capture(device):
    device.reset_input_buffer()
    device.write(b"r")
    deadline = time.monotonic() + 8
    while True:
        line = device.readline().strip()
        if line == b"AUDIO 16000 160000":
            break
        if line.startswith(b"ERROR"):
            raise RuntimeError(line.decode(errors="replace"))
        if time.monotonic() > deadline:
            raise RuntimeError("No audio header. Check the port and uploaded sketch.")
    print("RECORDING — wait about one second, then speak once; stay quiet afterward.", flush=True)
    audio = bytearray()
    deadline = time.monotonic() + 12
    while len(audio) < 160000 and time.monotonic() < deadline:
        audio.extend(device.read(min(4096, 160000 - len(audio))))
    if len(audio) != 160000:
        raise RuntimeError(f"Incomplete capture: {len(audio)}/160000 bytes. Nothing saved.")
    if device.readline().strip() != b"DONE":
        raise RuntimeError("Missing completion marker. Nothing saved.")
    return audio


def audio_stats(audio):
    samples = array("h", audio)
    if sys.byteorder != "little":
        samples.byteswap()
    return {"peak": max(abs(x) for x in samples),
            "rms": round(math.sqrt(sum(x*x for x in samples) / len(samples)), 2),
            "clipped_samples": sum(x >= 32767 or x <= -32768 for x in samples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Omit to auto-select a single USB serial device")
    parser.add_argument("--label", choices=["rocket", "other", "background"], default="rocket")
    parser.add_argument("--speaker", default="s01", help="Anonymous speaker ID; use a new ID for each person")
    parser.add_argument("--count", type=int, default=30, help="Total accepted recordings to reach for this speaker/label")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.speaker) or args.count < 1:
        parser.error("Use a simple speaker ID and a positive count.")
    import serial
    from serial.tools import list_ports
    port = args.port
    if not port:
        candidates = [p.device for p in list_ports.comports()
                      if p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM"))]
        if len(candidates) != 1:
            parser.error(f"Specify --port. Detected USB serial ports: {candidates}")
        port = candidates[0]
    folder = ROOT / args.speaker / args.label
    folder.mkdir(parents=True, exist_ok=True)
    accepted = sum(1 for p in folder.glob("*.json") if p.with_suffix(".wav").exists())
    if accepted >= args.count:
        print(f"Already have {accepted} recordings in {folder}. Nothing overwritten.")
        return
    print(f"Port: {port}\nSaving to: {folder}\nExisting clips: {accepted}/{args.count}")
    print("Each clip lasts five seconds. Enter starts; q quits. Use r afterward to retry.")
    print("Background mode: ignore the speaking cue and stay silent for the entire clip.")
    session = uuid.uuid4().hex
    with serial.Serial(port, 921600, timeout=1) as device:
        time.sleep(2)
        while accepted < args.count:
            if args.label == "rocket":
                prompt = "rocket"
                distance = "20–30 cm" if accepted < 10 else ("40–60 cm" if accepted < 20 else "about 1 m")
                print(f"\nClip {accepted + 1}/{args.count}: say 'rocket' once, from {distance}.")
                print("Use your natural voice; vary your pace slightly. Keep the fan as it is.")
            elif args.label == "other":
                prompt = OTHER_WORDS[accepted % len(OTHER_WORDS)]
                distance = "comfortable speaking distance"
                print(f"\nClip {accepted + 1}/{args.count}: say '{prompt}' once. Do not say rocket.")
            else:
                prompt, distance = "room background, no speech", "not applicable"
                print(f"\nClip {accepted + 1}/{args.count}: room/fan noise, no speech.")
            if input("Enter to start, q to quit: ").strip().lower() == "q":
                break
            audio = capture(device)
            stats = audio_stats(audio)
            print(f"Finished. Peak: {stats['peak']}/32768 | RMS: {stats['rms']} | Clipped: {stats['clipped_samples']}")
            if stats["clipped_samples"] or stats["peak"] == 0:
                print("Signal warning: consider retrying. These numbers do not verify the spoken word.")
            while True:
                choice = input("Enter to save, r to retry, q to quit without saving this clip: ").strip().lower()
                if choice in ("", "r", "q"):
                    break
            if choice == "q":
                break
            if choice == "r":
                continue
            stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12]
            wav_path = folder / f"{stem}.wav"
            with wav_path.open("xb") as handle:
                with wave.open(handle, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(audio)
            metadata = {"speaker": args.speaker, "label": args.label, "prompt": prompt,
                        "session": session, "suggested_distance": distance,
                        "sample_rate": 16000, "duration_seconds": 5,
                        "keyword_timing": "unannotated; crop/annotate before training",
                        "source": "ESP32 INMP441", **stats}
            wav_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
            accepted += 1
            print(f"Saved ({accepted}/{args.count}): {wav_path.name}")
    print(f"\nAccepted recordings: {accepted}/{args.count}\nFolder: {folder}")
    print("Run the same command to resume. Listen to a few clips before continuing.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Previously saved clips are kept.")
    except Exception as exc:
        print(f"Collection stopped: {exc}", file=sys.stderr)
        sys.exit(1)
