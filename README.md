# STOP voice activator for ESP32

A work-in-progress, open-source keyword detector for an **ESP32-WROOM-32E and INMP441 microphone**. The keyword is **STOP**, not the earlier placeholder “rocket.” The hardware owner uses Linux, Arduino IDE, ESP32 board package **3.3.11**, and **ESP32 Dev Module**.

## Start here

- **Friend / Claude Code:** read [AGENTS.md](AGENTS.md), [current status](docs/STATUS.md), then [development setup](docs/DEVELOPMENT.md).
- **Hardware owner:** use the [Git collaboration and board testing workflow](docs/COLLABORATION.md).
- **Current firmware:** [complete V10-R1 sketch](outputs/live_stop_reviewed_v10/live_stop_reviewed_v10.ino). It runs, but falsely detects some similar words. This is a baseline, not a finished solution.

**V13 is incomplete and is not ready to upload.** Training stopped after 13 completed epochs, during epoch 14. No training process was found at handoff. V11 and V12 failed validation. No training or compilation was performed while preparing this repository.

## Hardware

| INMP441 pin | ESP32 connection |
|---|---|
| VDD | 3.3 V |
| GND | GND |
| L/R | GND (left channel) |
| SCK / BCLK | GPIO 26 |
| WS / LRCLK | GPIO 33 |
| SD | GPIO 32 |

The microphone has produced clear 16 kHz recordings. The live firmware captures 32-bit I2S slots and converts to PCM16 by shifting right 16 bits. Keep capture and training preprocessing consistent.

## Included

- Complete baseline Arduino sketch, model, frontend, self-test vectors; mic recorder and sine-model runtime test.
- Current training/data preparation code and its imported helper modules.
- V10 baseline artifacts, V11/V12 rejected-run evidence and best checkpoints, V13 partial checkpoints and exact training source snapshots.
- **32 accepted personal voice recordings**: 16 training, 8 validation, 8 reused test clips; plus one fan-noise recording. These files are deliberately included so the friend can reproduce local checks without the ESP32.
- Public dataset download URLs/checksums, source attribution, historical logs and collaboration instructions.

Large public audio archives, extracted public data, feature caches, installed packages, compiled binaries and rejected personal recording takes are excluded. Rebuild public-data caches on the friend's machine when training is explicitly requested. The complete original workspace remains on the owner's computer.

## Project boundaries

Target: local KWS, then triggered remote ASR streaming; under 256 KB RAM and under 10% idle CPU. **Neither resource limit has been demonstrated.** Networking/ASR is not implemented. Historical inference timing is about 26.6 ms; `work%` is pipeline wall time, not total CPU utilization.

Dataset attribution: [PUBLIC_DATA_SOURCES.md](outputs/PUBLIC_DATA_SOURCES.md). No blanket repository license has been assigned by this handoff; preserve source-specific notices and attribution.
