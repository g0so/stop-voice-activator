# V14 — fails original gates; shipped as baseline-improvement board candidate

Trained 2026-09-29 on the friend's Windows 11 PC (Python 3.13.14, tensorflow-cpu 2.20.0, NumPy 2.5.3 — pinned lockfile versions; CPU only).

## What was tried

- Batch-normalized DS-CNN 16/24/32 from random weights (same architecture as V13), full shuffle, seed 2026092911.
- Same expanded features as V11–V13 (regenerated locally; counts identical: 150,252 / 16,552 / 13,891).
- **New:** `--streaming-supplement` — 1,456 training-only rolling windows from the 16 reviewed training recordings (816 rolling negatives, 640 augmented positives), sample weight 8. No validation/test recordings used.
- Early stopping after epoch 35 (best validation loss at epoch 23). Checkpoints best, 10, 20, 30 evaluated with BUILTIN_REF.

## Result

No checkpoint/threshold passes all gates, so nothing was frozen and the expanded test was **not** scored.

Lowest threshold at which every false-activation gate passes (START/SHORT/STARK/SHOP, SC, MSWC, LibriSpeech, background, local negatives):

| Checkpoint | Threshold | SC STOP recall (need 0.80) | MSWC STOP recall (need 0.70) | Local STOP worst phase | START false |
|---|---|---|---|---|---|
| best (epoch 23) | 0.9805 | 0.591 | 0.289 | 2/4 | 5/182 |
| epoch 10 | 0.9492 | 0.591 | 0.353 | 3/4 | 5/182 |
| epoch 20 | 0.9492 | 0.591 | 0.324 | 3/4 | 5/182 |
| epoch 30 | 0.9492 | 0.586 | 0.279 | 3/4 | 6/182 |

Same measure for V12 best: SC 0.504, MSWC 0.265, local worst phase 0/4.

## Interpretation

- The streaming supplement appears to fix the local rolling-window false triggers: at threshold 0.875 V12 best triggered on 3/4 local negative recordings, V14 epoch 30 on 0/4 while keeping ≥3/4 local STOP at every phase.
- The remaining failure is the STOP-vs-similar-word trade-off: rejecting START/MSWC confusables forces a threshold that loses too much STOP recall. This has persisted across V11–V14 with the same 5.9k-parameter network and is the likely capacity limit.
- Batch-norm folds cleanly: converted model 13,688 bytes, int8-only, ops CONV_2D / DEPTHWISE_CONV_2D / FULLY_CONNECTED / RESHAPE / SOFTMAX (the existing sketch's resolver).

Not approved under the original gates. V10-R1 remains the reference baseline.

## Baseline-improvement candidate (explicit collaborator decision)

After V14 and V15 were rejected, the collaborators chose to ship a candidate that clearly beats the deployed V10-R1 rather than one that passes the V11 gates. Rule, written to frozen_selection.json **before** any test access: keep V10's threshold 0.8671875 unchanged; pick the checkpoint that matches V10's MSWC STOP recall with zero local negative triggers and 4/4 local STOP at every phase. Selected: **epoch_20**, SHA256 `4be984725547bc3702a6ef3c455a151096eb8138a400fa284b8fb670a5248429`, 13,688 bytes.

Validation, same threshold (V10 computed on the same regenerated features):

| Measure | V14 epoch_20 | V10-R1 |
|---|---|---|
| SC STOP recall | 0.746 | 0.801 |
| MSWC STOP recall | 0.539 | 0.534 |
| SC other-word FP | 0.55% | 4.81% |
| MSWC other-word FP | 2.88% | 36.0% |
| LibriSpeech FP | 0.12% | 6.12% |
| START / SHORT / STARK / SHOP | 18/182, 0/195, 1/8, 0/3 | 97/182, 11/195, 7/8, 1/3 |
| Local validation negatives triggered / worst-phase STOP | 0 / 4 of 4 | 0 / 4 of 4 |

Test, scored once after freezing (metrics.json, baseline_v10_comparison.json):

| Measure | V14 | V10-R1 |
|---|---|---|
| SC STOP recall | 285/354 (80.5%) | 305/354 (86.2%) |
| SC other-word FP | 70/9,391 | 578/9,391 |
| MSWC STOP recall | 115/191 (60.2%) | 101/191 (52.9%) |
| MSWC other-word FP | 76/2,274 | 937/2,274 |
| START / STAR / SHORT / STOPPED (MSWC) | 13/162, 16/161, 0/178, 19/91 | 97/162, 121/161, 16/178, 54/91 |
| LibriSpeech 1 s windows FP | 2/1,173 | 86/1,173 |
| Continuous LibriSpeech replay (333 test utterances, 0.57 h, worst phase) | 68 false activations/h | 956 false activations/h |
| Reused local test (8 clips, 10 phases) | STOP 4/4 at every phase; **SHOP 02 triggered 5/10 phases (max 0.969), START 04 3/10 (max 0.926)** | STOP 4/4, negatives 0/4 |

Honest reading: large desktop reduction in similar-word and continuous-speech false activations, somewhat lower Speech Commands recall, and a **regression on the owner's own SHOP/START test recordings** (single speaker, eight reused clips). ~68 false activations per hour of continuous read speech is still far from a usable always-on detector. The board test decides whether V14 is better in practice.

Host frontend parity (Windows, zig-built library, BUILTIN_REF): 96 windows, max float diff 1.13e-6, zero quantized-input and model-output differences (frontend_parity_reference.json). Arduino compilation not performed on this PC. Packaged sketch: ../live_stop_expanded_v14/.

## Windows portability notes

- `fetch_expanded_data.py`: Windows file lock fallback (msvcrt) where `fcntl` is unavailable.
- ffmpeg 9.0.2 (winget Gyan.FFmpeg) for audio conversion.
- Host frontend parity library built with `ziglang` 0.16.0 (pip, venv only) instead of g++; V10 parity reproduced exactly (work/frontend_parity_v10_windows.json: max float diff 1.132e-6, max quantized diff 1, identical outputs).
