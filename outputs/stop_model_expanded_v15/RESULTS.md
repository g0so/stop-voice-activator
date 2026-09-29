# V15 — rejected on validation (test unscored)

Same as V14 (batch norm, streaming supplement, same features, gates and seed) but DS-CNN widths **32/48/64** instead of 16/24/32 (`--widths 32,48,64`). Purpose: test whether model capacity limits the STOP-vs-similar-word trade-off.

Early stopping after 19 epochs; best validation loss at epoch 7 (0.180; V14 best 0.195). Validation loss was noisy (0.18–0.28). Checkpoints best and epoch 10 evaluated with BUILTIN_REF; neither passes.

Lowest threshold at which every false-activation gate passes:

| Checkpoint | Threshold | SC STOP recall (need 0.80) | MSWC STOP recall (need 0.70) | Local STOP worst phase |
|---|---|---|---|---|
| best | 0.9961 | 0.515 | 0.221 | 2/4 |
| epoch 10 | 0.9336 | 0.655 | 0.279 | 1/4 |

No better than V14 at matched false activations, while roughly 4x the parameters and slower on the MCU. Conclusion: capacity is not the bottleneck. The largest MSWC false-activation sources are "stopped" (e.g. 59/132 at 0.875 for best), "start" and "star".

Not approved for device. Test not scored.
