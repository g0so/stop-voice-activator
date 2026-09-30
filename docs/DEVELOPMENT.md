# Development on the friend's computer

Commands below are reference instructions, **not authorization to run training or builds**. Work from the repository root. No ESP32 is needed to inspect code, train, or replay included WAV files.

## Environment

Observed environment: Linux, Python 3.13.12, tensorflow-cpu 2.20.0, NumPy 2.5.3. The included requirements.txt records the original installed packages, including Keras needed to load .keras checkpoints. Use a separate environment. If a platform cannot install these exact versions, document substitutions and recheck conversion/reference parity; do not silently overwrite the lockfile.

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

System programs used: curl (downloads), ffmpeg (audio conversion), g++ (optional host frontend parity). Arduino IDE/CLI is only needed for firmware compilation. The hardware owner already has ESP32 board package 3.3.11. Its existing TFLite Micro runtime worked; no new activation SDK is needed.

## Recreate public training inputs (large downloads)

```bash
.venv/bin/python outputs/fetch_expanded_data.py
.venv/bin/python outputs/prepare_expanded_audio.py --source all
.venv/bin/python outputs/build_expanded_features.py
```

Allow several GB of downloads and substantially more disk for extracted audio/features. Sources and publisher checksums are in outputs/expanded_sources.json. Data is downloaded directly from public publishers. Keep original notices in extracted data. The reviewed recordings and fan noise needed by the feature builder are already included.

The cache directory name `work/expanded_features_v11` is intentional: V11/V12/V13 share those same features and partitions. The V13 experiment_sources folder preserves the code at its launch. Current helper scripts have only documented handoff portability corrections.

## Partial V13

After inputs exist, the selection-only command can evaluate the **available partial-run** checkpoints without training:

```bash
.venv/bin/python outputs/train_expanded_keyword.py --select-only --output-dir stop_model_expanded_v13 --batchnorm --epochs 60
```

The script's experiment plan is rewritten by this command and describes the configured maximum, not the actual 13 completed epochs. Keep HANDOFF_STATUS.json and training_history.csv as evidence; explicitly describe the partial run in any report. Do not run selection-only after a frozen selection already exists. It will evaluate test automatically only if validation passes.

To train again, use a new output version. `--warmstart` loads a checkpoint but resets the optimizer and is **fine-tuning, not exact training resume**. The batchnorm flag currently requires a fresh model when combined with the trainer's arguments, so inspect its constraints before choosing a command. Do not overwrite V13 or pretend interrupted work resumed exactly.

## Frontend / numerical contract

- 16 kHz mono PCM16, one-second inputs.
- 480-sample frame, 320-sample hop, FFT512; 49 frames × 24 mel bands (80–7600 Hz).
- Per-frame mean removal, symmetric Hann, power FFT/512; logarithmic features from audio_features.py.
- Subtract each mel band's temporal mean over the 49-frame window.
- Input shape [1,49,24,1], int8; output classes background=0, other=1, STOP=2.
- Quantized desktop checks and test vectors use BUILTIN_REF. Preserve threshold, scale, zero point, rounding and trigger logic.

The host frontend parity source is tools/frontend_wrapper.cpp. Example future build (not performed at handoff):

```bash
mkdir -p work
c++ -std=c++17 -O2 -shared -fPIC -I outputs/live_stop_reviewed_v10 tools/frontend_wrapper.cpp outputs/live_stop_reviewed_v10/frontend.cpp -o work/frontend_check.so
```

Then run, substituting the chosen model path:

```bash
.venv/bin/python tools/check_frontend.py outputs/stop_model_reviewed_v10/stop_int8.tflite
```

This writes work/frontend_parity_latest.json; archive it with the candidate's results. It does not run during handoff preparation.

The check compares its centered_features output against audio_features.features followed by temporal centering, across rotating ring offsets. Previous host check covered 96 windows, max float difference 1.132e-6 and max quantized-input difference 1, with identical model outputs. A new model's input scale can change quantization; repeat parity for it and retain the report. Host checks do not replace the board self-test.

## Export and delivery (only after validation passes)

The trainer emits stop_int8.tflite, stop_model_data.h and test_vectors.h after freezing/evaluating a candidate. Run continuous negative replay with an explicit model directory:

```bash
.venv/bin/python outputs/evaluate_expanded_continuous.py --model-dir stop_model_expanded_v13
.venv/bin/python outputs/package_expanded_firmware.py --version 13
```

Substitute the actual passing version. Neither command is currently appropriate for the incomplete V13. The packager includes all frontend sources, the model and reference vectors. Threshold must match frozen_selection.json. Compare generated source with the baseline before delivery.

Have Arduino IDE/CLI compile for esp32:esp32:esp32 (ESP32 Dev Module), core 3.3.11, if authorized and available. Record compiler result and resource sizes. Commit the complete sketch folder, small .tflite model, provenance, evaluation report and instructions together. No auto-flashing from the friend's machine.

## V14 triggered streaming and local ASR

The integration sketch is `outputs/live_stop_expanded_v14_streaming/live_stop_expanded_v14_streaming.ino`. Edit its `network_config.h`, then start the local receiver from the repository root:

```bash
server/.venv/bin/python server/voice_activation_server.py --model tiny.en
```

For transport-only testing, use `--no-asr`. The dashboard is available at `http://127.0.0.1:8080`. See `server/README.md` for setup and `server/TEST_REPORT.md` for host-only verification. The final SIH latency, CPU and peak-RAM evidence must come from the physical ESP32 run, not the local test client.
