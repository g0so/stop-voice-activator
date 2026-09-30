#!/usr/bin/env python3
"""Receive triggered ESP32 PCM audio, save WAV files and run local ASR."""

from __future__ import annotations

import argparse
import json
import socketserver
import struct
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from adpcm import CODEC_IMA_ADPCM, CODEC_PCM16, decode_ima_adpcm
from asr_backend import WhisperBackend
from protocol import (
    AUDIO,
    AUDIO_PREFIX,
    END,
    END_STRUCT,
    HELLO,
    HELLO_STRUCT,
    PING,
    PING_STRUCT,
    TRIGGER,
    TRIGGER_STRUCT,
    ProtocolError,
    recv_frame,
)


def wrapped_delta_ms(later: int, earlier: int) -> int:
    return (later - earlier) & 0xFFFFFFFF


@dataclass
class Capture:
    activation_id: int
    device_trigger_ms: int
    score: float
    pre_roll_ms: int
    capture_ms: int
    sample_rate: int
    channels: int
    sample_bits: int
    wav_path: Path
    metadata_path: Path
    wave_file: wave.Wave_write
    trigger_received_monotonic: float = field(default_factory=time.monotonic)
    first_audio_received_monotonic: float | None = None
    first_client_send_ms: int | None = None
    frames: int = 0
    bytes_received: int = 0
    encoded_bytes_received: int = 0
    sequence_gaps: int = 0
    expected_sequence: int = 0


class SharedState:
    def __init__(self, output_dir: Path, asr: WhisperBackend | None) -> None:
        self.output_dir = output_dir
        self.asr = asr
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="asr")
        self.lock = threading.Lock()
        self.latest: dict[str, Any] = {
            "state": "waiting",
            "message": "Waiting for ESP32 connection",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def update(self, **values: Any) -> None:
        with self.lock:
            self.latest.update(values)
            self.latest["updated_at"] = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.latest)

    def transcribe(self, wav_path: Path, metadata_path: Path, metadata: dict[str, Any]) -> None:
        if self.asr is None:
            self.update(state="saved", message=f"Saved {wav_path.name}", **metadata)
            return

        def job() -> None:
            self.update(state="transcribing", message=f"Transcribing {wav_path.name}", **metadata)
            try:
                result = self.asr.transcribe(wav_path)
                metadata["asr"] = result
                metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                print(f"TRANSCRIPT #{metadata['activation_id']}: {result['text']}", flush=True)
                self.update(
                    state="complete",
                    message=result["text"] or "No speech recognized",
                    transcript=result["text"],
                    **metadata,
                )
            except Exception as exc:  # Keep the receiver alive if ASR fails.
                metadata["asr_error"] = str(exc)
                metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                print(f"ASR ERROR: {exc}", flush=True)
                self.update(state="asr_error", message=str(exc), **metadata)

        self.executor.submit(job)


class VoiceHandler(socketserver.BaseRequestHandler):
    server: "VoiceTCPServer"

    def handle(self) -> None:
        peer = f"{self.client_address[0]}:{self.client_address[1]}"
        print(f"ESP32 connected from {peer}", flush=True)
        self.server.state.update(state="connected", message=f"ESP32 connected from {peer}", peer=peer)
        sample_rate, sample_bits, channels, model_version = 16000, 16, 1, None
        capture: Capture | None = None
        try:
            while True:
                frame = recv_frame(self.request)
                received_at = time.monotonic()
                if frame.frame_type == HELLO:
                    if len(frame.payload) != HELLO_STRUCT.size:
                        raise ProtocolError("invalid HELLO length")
                    sample_rate, sample_bits, channels, model_version, frame_samples, _ = HELLO_STRUCT.unpack(frame.payload)
                    if (sample_rate, sample_bits, channels) != (16000, 16, 1):
                        raise ProtocolError("only 16 kHz mono PCM16 is supported")
                    print(f"HELLO model=V{model_version} rate={sample_rate} frame={frame_samples}", flush=True)
                    self.server.state.update(
                        state="ready",
                        message=f"V{model_version} connected and listening",
                        model_version=model_version,
                        sample_rate=sample_rate,
                    )
                elif frame.frame_type == TRIGGER:
                    if len(frame.payload) != TRIGGER_STRUCT.size:
                        raise ProtocolError("invalid TRIGGER length")
                    activation_id, device_ms, score_q15, pre_ms, capture_ms, _ = TRIGGER_STRUCT.unpack(frame.payload)
                    if capture is not None:
                        capture.wave_file.close()
                    stamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
                    wav_path = self.server.state.output_dir / f"activation_{activation_id:06d}_{stamp}.wav"
                    metadata_path = wav_path.with_suffix(".json")
                    wav_file = wave.open(str(wav_path), "wb")
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(sample_bits // 8)
                    wav_file.setframerate(sample_rate)
                    capture = Capture(
                        activation_id=activation_id,
                        device_trigger_ms=device_ms,
                        score=score_q15 / 32767.0,
                        pre_roll_ms=pre_ms,
                        capture_ms=capture_ms,
                        sample_rate=sample_rate,
                        channels=channels,
                        sample_bits=sample_bits,
                        wav_path=wav_path,
                        metadata_path=metadata_path,
                        wave_file=wav_file,
                        trigger_received_monotonic=received_at,
                    )
                    print(f"TRIGGER #{activation_id} score={capture.score:.4f}", flush=True)
                    self.server.state.update(
                        state="receiving",
                        message=f"Receiving activation #{activation_id}",
                        activation_id=activation_id,
                        score=capture.score,
                    )
                elif frame.frame_type == AUDIO:
                    if len(frame.payload) < AUDIO_PREFIX.size or (len(frame.payload) - AUDIO_PREFIX.size) % 2:
                        raise ProtocolError("invalid AUDIO payload")
                    if capture is None:
                        raise ProtocolError("AUDIO received before TRIGGER")
                    activation_id, sequence, sample_index, client_send_ms, predictor, step_index, codec, sample_count = AUDIO_PREFIX.unpack_from(frame.payload)
                    if activation_id != capture.activation_id:
                        raise ProtocolError("activation id changed inside capture")
                    if sequence != capture.expected_sequence:
                        capture.sequence_gaps += 1
                    capture.expected_sequence = sequence + 1
                    encoded = frame.payload[AUDIO_PREFIX.size :]
                    if codec == CODEC_PCM16:
                        if len(encoded) != sample_count * 2:
                            raise ProtocolError("PCM payload length does not match sample count")
                        pcm = encoded
                    elif codec == CODEC_IMA_ADPCM:
                        try:
                            pcm = decode_ima_adpcm(encoded, predictor, step_index, sample_count)
                        except ValueError as exc:
                            raise ProtocolError(str(exc)) from exc
                    else:
                        raise ProtocolError(f"unsupported audio codec {codec}")
                    if capture.first_audio_received_monotonic is None:
                        capture.first_audio_received_monotonic = received_at
                        capture.first_client_send_ms = client_send_ms
                        server_delay = (received_at - capture.trigger_received_monotonic) * 1000.0
                        device_delay = wrapped_delta_ms(client_send_ms, capture.device_trigger_ms)
                        print(
                            f"FIRST AUDIO #{activation_id}: server trigger-frame-to-audio={server_delay:.2f} ms, "
                            f"device trigger-to-send={device_delay} ms, sample_index={sample_index}",
                            flush=True,
                        )
                    capture.wave_file.writeframesraw(pcm)
                    capture.frames += 1
                    capture.bytes_received += len(pcm)
                    capture.encoded_bytes_received += len(encoded)
                elif frame.frame_type == END:
                    if len(frame.payload) != END_STRUCT.size:
                        raise ProtocolError("invalid END length")
                    activation_id, sent_samples, dropped_samples, device_trigger_ms, first_send_ms = END_STRUCT.unpack(frame.payload)
                    if capture is None or activation_id != capture.activation_id:
                        raise ProtocolError("END does not match active capture")
                    capture.wave_file.close()
                    first_server_ms = None
                    if capture.first_audio_received_monotonic is not None:
                        first_server_ms = (capture.first_audio_received_monotonic - capture.trigger_received_monotonic) * 1000.0
                    metadata = {
                        "activation_id": activation_id,
                        "model_version": model_version,
                        "score": capture.score,
                        "sample_rate": sample_rate,
                        "sample_bits": sample_bits,
                        "channels": channels,
                        "pre_roll_ms": capture.pre_roll_ms,
                        "capture_after_trigger_ms": capture.capture_ms,
                        "sent_samples": sent_samples,
                        "received_samples": capture.bytes_received // 2,
                        "encoded_audio_bytes": capture.encoded_bytes_received,
                        "pcm_audio_bytes": capture.bytes_received,
                        "audio_payload_reduction_percent": round(
                            100.0 * (1.0 - capture.encoded_bytes_received / max(1, capture.bytes_received)), 2
                        ),
                        "dropped_samples": dropped_samples,
                        "sequence_gaps": capture.sequence_gaps,
                        "device_trigger_to_first_send_ms": wrapped_delta_ms(first_send_ms, device_trigger_ms) if first_send_ms else None,
                        "server_trigger_frame_to_first_audio_ms": round(first_server_ms, 3) if first_server_ms is not None else None,
                        "wav_path": str(capture.wav_path),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    capture.metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                    print(
                        f"END #{activation_id}: {metadata['received_samples']} samples, "
                        f"dropped={dropped_samples}, gaps={capture.sequence_gaps}, wav={capture.wav_path.name}",
                        flush=True,
                    )
                    self.server.state.transcribe(capture.wav_path, capture.metadata_path, metadata)
                    capture = None
                elif frame.frame_type == PING:
                    if len(frame.payload) != PING_STRUCT.size:
                        raise ProtocolError("invalid PING length")
                else:
                    raise ProtocolError(f"unknown frame type {frame.frame_type}")
        except EOFError:
            print(f"ESP32 disconnected: {peer}", flush=True)
        except (ProtocolError, OSError, struct.error) as exc:
            print(f"CONNECTION ERROR {peer}: {exc}", flush=True)
        finally:
            if capture is not None:
                capture.wave_file.close()
            self.server.state.update(state="waiting", message="ESP32 disconnected")


class VoiceTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: SharedState) -> None:
        self.state = state
        super().__init__(address, VoiceHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: "DashboardServer"

    def do_GET(self) -> None:  # noqa: N802
        snapshot = self.server.state.snapshot()
        if self.path == "/api/status":
            body = json.dumps(snapshot, indent=2).encode()
            content_type = "application/json"
        elif self.path == "/" or self.path.startswith("/?"):
            safe_json = json.dumps(snapshot).replace("<", "\\u003c")
            body = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"2\">
<title>Voice Activator</title><style>
body{{font-family:system-ui;background:#071822;color:#eef7f8;max-width:850px;margin:5rem auto;padding:0 2rem}}
h1{{color:#22d3c5}} .state{{font-size:1.5rem}} pre{{background:#0d2733;padding:1rem;overflow:auto}}
</style></head><body><h1>ESP32 Voice Activator</h1>
<p class=\"state\">{snapshot.get('message', '')}</p><pre>{safe_json}</pre></body></html>""".encode()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], state: SharedState) -> None:
        self.state = state
        super().__init__(address, DashboardHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dashboard-port", type=int, default=8080)
    parser.add_argument("--output-dir", type=Path, default=Path("server/captures"))
    parser.add_argument("--model", default="tiny.en", help="faster-whisper model name or local model path")
    parser.add_argument("--language", default="en", help="language code; use 'auto' for detection")
    parser.add_argument("--no-asr", action="store_true", help="receive and save WAV files without transcription")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    language = None if args.language == "auto" else args.language
    asr = None if args.no_asr else WhisperBackend(args.model, language)
    state = SharedState(args.output_dir.resolve(), asr)
    tcp = VoiceTCPServer((args.host, args.port), state)
    dashboard = DashboardServer((args.host, args.dashboard_port), state)
    threading.Thread(target=dashboard.serve_forever, name="dashboard", daemon=True).start()
    print(f"Voice receiver: {args.host}:{args.port}", flush=True)
    print(f"Dashboard: http://127.0.0.1:{args.dashboard_port}", flush=True)
    print(f"Captures: {state.output_dir}", flush=True)
    print("ASR: disabled" if asr is None else f"ASR: faster-whisper {args.model}", flush=True)
    try:
        tcp.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.", flush=True)
    finally:
        tcp.shutdown()
        dashboard.shutdown()
        state.executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
