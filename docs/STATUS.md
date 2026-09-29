# State at Git handoff

## Deployment status

**V10-R1 is the only included previously compiled live detector.** The owner says it runs, but START, SHORT, STARK, STOT and other words can trigger it. Earlier physical inference timing was approximately 26.6 ms. The final R1 startup parity log was not supplied; do not infer a measured pass from the user's general “working” report.

V10 model: 13,288 bytes, threshold 0.8671875, 24 KiB reserved arena, one inference every 200 ms. Historical build: 399,888 bytes flash and 59,916 bytes static RAM. Complete firmware is outputs/live_stop_reviewed_v10/.

## Expanded experiments

| Experiment | State | Meaning |
|---|---|---|
| V11 | Rejected on validation | Too many misses when threshold rejects similar words. Small shuffle buffer preserved dataset ordering. |
| V12 | Rejected on validation | Full shuffle and stronger local-negative weighting improved some results but did not pass combined gates. |
| V14 | Rejected on original gates; shipped as **baseline-improvement board candidate** | Batch norm + streaming supplement, 16/24/32. No checkpoint passes the V11 gates. By explicit collaborator decision, epoch_20 frozen at V10's threshold 0.8671875 (no tuning) before test, because it cuts V10's validation false activations ~5–50x at equal MSWC recall. Sketch: outputs/live_stop_expanded_v14/. Board test pending. |
| V15 | Rejected on validation | Same as V14 with widths 32/48/64. No better at matched false activations: capacity is not the bottleneck. Test unscored. |
| V13 | Interrupted | 13 epochs completed; log ended at epoch 14/60. best.keras and epoch_10.keras preserved. No validation selection, exported deployment model or test evaluation. No process running at handoff. |

V13 adds batch normalization during training, intended to fold into convolutions when exported. Folding, operation compatibility and accuracy remain unchecked. Historical model directories may reference intermediate checkpoints not included here; best checkpoints and evidence are retained. V13 has both available checkpoints. This snapshot is sufficient to continue investigation, not to reproduce every old experiment byte-for-byte without regenerating data.

## Data

Prepared on the owner's PC: Speech Commands v0.02 (105,829 clips), selected MSWC (25,741), non-STOP LibriSpeech sentences (2,689). Total 134,259 sources; 5,790 STOP clips across all partitions. Feature cache contained 150,252 training, 16,552 validation and 13,891 test examples. Downloads/caches are excluded from Git and can be regenerated.

MSWC selected totals: SHORT 1,876; START 1,701; STARK 82; SHOP 33; STOP 1,918. No STOT examples. VALID flags are automatic, not manual verification of every crop. Speaker hashes separate splits within each corpus, not across unrelated corpus identities.

The included reviewed manifest selects exactly 16/8/8 training/validation/test personal recordings. All are accepted five-second clips; test has been reused in earlier development and is not fresh independent evidence. Only these accepted clips, their metadata and fan noise are included, not rejected takes.

## Diagnostic evidence

V10 at its existing threshold on MSWC validation: STOP 109/204; false START 97/182, SHORT 11/195, STARK 7/8, SHOP 1/3.

V12 best at threshold 0.875: SC STOP recall 73.45%; MSWC STOP recall 62.75%; false START 19/182, SHORT 1/195, STARK 0/8, SHOP 0/3. Three of four local negative recordings triggered at some rolling-window position. It was rejected; the expanded test remained unscored.

V10's small original local test passed 4/4 STOP and 0/4 negatives across ten phases, but this did not generalize to new similar words. Reference-runtime historical metrics take precedence over older accelerated-desktop metrics.

## Next investigation, when authorized

1. Inspect V13 partial history/checkpoints and decide between evaluating existing checkpoints or a new versioned run. Do not restart automatically or call this a finished 60-epoch run.
2. Recreate public audio/features on the friend's machine if needed. Generated manifests contain machine-specific absolute paths: regenerate them, do not copy them from another machine.
3. Existing build_streaming_supplement.py creates 1,456 training-only examples from reviewed audio (816 rolling negatives, 640 augmented positives). These were prepared separately on the owner's PC but **not wired into V13 training**. They may address window-position false triggers. Do not claim they were already used.
4. Select/freeze a passing candidate, evaluate test and full negative utterances, check host frontend parity, then package a complete sketch for the owner. Never silently weaken acceptance gates.

Still unimplemented: triggered network audio streaming, ASR server, end-to-end latency measurement. Still unverified: total idle CPU and whole-application peak RAM. A successful KWS model does not finish the hackathon project.
