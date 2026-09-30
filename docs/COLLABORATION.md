# Git and board-test workflow

The shared repository is `https://github.com/g0so/stop-voice-activator.git`.

## Before starting work

```bash
git status
git fetch origin
git pull --ff-only
```

Do not discard uncommitted work. If `git status` is not clean, commit or deliberately stash it before switching branches.

## Development branches

Use one branch for one logical change. Model experiments must use a new versioned output directory. Preserve V10-R1, V14, V15 and the V14 streaming integration as historical evidence.

A firmware or model handoff should contain:

- complete sketch directory;
- model and model header;
- frontend sources and tables;
- self-test vectors;
- model SHA256 and frozen threshold;
- validation and test evidence;
- compilation report;
- board test instructions and limitations.

Do not commit public audio archives, feature caches, virtual environments, compiled binaries, ASR model downloads, captures containing new speech or Wi-Fi credentials.

## Current candidate

- Sketch: `outputs/live_stop_expanded_v14_streaming/live_stop_expanded_v14_streaming.ino`
- Server: `server/voice_activation_server.py`
- Model: frozen V14 epoch 20
- Model SHA256: `4be984725547bc3702a6ef3c455a151096eb8138a400fa284b8fb670a5248429`
- Threshold: `0.8671875`
- Target board: ESP32 Dev Module
- Target ESP32 core: 3.3.11

## Hardware owner procedure

1. Pull the candidate commit and record its hash.
2. Edit `network_config.h` locally with the real Wi-Fi values. Restore the placeholders before committing.
3. Start the server using [`docs/QUICKSTART.md`](QUICKSTART.md).
4. Upload the complete streaming sketch.
5. Save the full 115200-baud startup log.
6. Stop immediately if any self-test line reports `ERROR` or the maximum reference difference exceeds 3.
7. Run the STOP and confusable-word sequence from the quick start.
8. Save the WAV and JSON records from `server/captures/` outside the repository unless they are explicitly reviewed for sharing.
9. Fill a new copy of `hardware-tests/STREAMING_TEMPLATE.md`.
10. Commit the report and sanitized serial log, then push the results branch.

## Result handoff

The report must identify:

- tested commit hash;
- board and core version;
- model hash and threshold;
- room, distance and noise conditions;
- detections and false activations by word;
- dropped samples and sequence gaps;
- device and server latency fields;
- any reset, disconnect or self-test issue.

Avoid overwriting an earlier report. Use a date and model name, for example `hardware-tests/2026-09-30-v14-streaming.md`.

## Fallback

V10-R1 remains under `outputs/live_stop_reviewed_v10/`. If the combined V14 integration cannot pass its startup self-test or reliably capture audio, use V10-R1 for the local keyword demonstration and report the V14 transport result separately. Do not modify thresholds or reference tolerance during the comparison.
