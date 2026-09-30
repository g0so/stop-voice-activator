# V16 — rejected on validation

V16 was the single final bounded model experiment authorized after the physical
V14 test. It targeted the live START/STOT-family false activations without
using any physical-test capture for training or selection.

## Experiment

- Same batch-normalized DS-CNN 16/24/32 architecture and prepared public
  feature cache as V14.
- Same training-only rolling-window supplement as V14.
- Additional 4x weight for MSWC `start`, `star`, `stark` and `stopped`
  negatives.
- Additional 1.5x weight for STOP examples to counter the stronger negative
  weighting.
- Added `star` and `stopped` to the separately enforced critical-word gates.
- Seed: 2026092911.
- Early stopping completed after 15 epochs; validation loss was best at epoch
  3. Preserved checkpoints: `best.keras` and `epoch_10.keras`.
- Checkpoint conversion and selection used TFLite BUILTIN_REF.

## Result

Neither checkpoint passed validation. The expanded held-out test was not
evaluated and no deployment firmware was packaged.

At V14's deployed threshold, 0.8671875:

| Measure | V16 best | V16 epoch 10 | V14 epoch 20 |
|---|---:|---:|---:|
| Speech Commands STOP recall | 75.9% | 69.0% | 74.6% |
| MSWC STOP recall | 60.3% | 27.5% | 53.9% |
| Speech Commands other-word FP | 2.03% | 0.49% | 0.55% |
| MSWC other-word FP | 4.14% | 0.57% | 2.88% |
| START false / 182 | 18 | 1 | 18 |
| Local negative clips triggered | 2 | 0 | 0 |
| Worst-phase local STOP | 4/4 | 3/4 | 4/4 |

The epoch-10 checkpoint sharply reduced START false activations, but MSWC STOP
recall collapsed. Its lowest threshold satisfying all configured false-
activation gates was 0.91796875, where Speech Commands STOP recall was 59.3%
and MSWC STOP recall was 14.2%. The best checkpoint retained more recall but
did not control false activations.

## Interpretation

Targeted reweighting moved the existing trade-off rather than solving it.
V16 cannot replace V14: the checkpoint with useful hard-negative rejection
misses too many STOP examples, while the higher-recall checkpoint still fails
the false-activation gates. Preserve V14 as the physically demonstrated
integration candidate and report its accuracy limitation honestly.
