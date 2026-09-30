# Current project status

## Deployment status

The **V16 comparison firmware has run on the physical board**. In the owner's final live demonstration, STOP activated **5/5 times** and START did not activate in the follow-up check. STOT still activated. Exact repetition counts were not retained for the final START and STOT checks, so those two observations remain qualitative. This board result replaces the older V14 behavior as the current live demonstration result, but it does not override V16's rejected public validation.

V10-R1 also ran previously on the board, with known START, SHORT, STARK and STOT confusion. Earlier physical inference timing was approximately 26.6 ms.

V10 model: 13,288 bytes, threshold 0.8671875, 24 KiB reserved arena, one inference every 200 ms. Historical build: 399,888 bytes flash and 59,916 bytes static RAM. Complete firmware is outputs/live_stop_reviewed_v10/.

The **V14 streaming integration** is the current end-to-end candidate. It preserves the V14 model and frontend, adds persistent TCP, 750 ms pre-roll, five seconds of following audio, IMA ADPCM compression, loss telemetry and a local faster-whisper server. The owner's GCC 14.2.0 toolchain initially exposed a `.dram0.bss` overflow from the global 48 KiB audio ring. The ring now uses checked internal-heap allocation, and recompilation with ESP32 core 3.3.12 passes. A physical run passed the nine-vector self-test with maximum reference difference 0 and completed 25 captures totaling 2,300,000 samples with zero drops or sequence gaps.

## Expanded experiments

| Experiment | State | Meaning |
|---|---|---|
| V11 | Rejected on validation | Too many misses when threshold rejects similar words. Small shuffle buffer preserved dataset ordering. |
| V12 | Rejected on validation | Full shuffle and stronger local-negative weighting improved some results but did not pass combined gates. |
| V14 | Rejected on original gates; physically tested as a **baseline-improvement candidate** | Batch norm + streaming supplement, 16/24/32. Physical transport passed, but the controlled run detected only 3/10 STOP and falsely activated on START 4/5, STARK 2/5 and STOT 5/5. It is not a finished detector. |
| V15 | Rejected on validation | Same as V14 with widths 32/48/64. No better at matched false activations: capacity is not the bottleneck. Test unscored. |
| V16 | Rejected on validation; final physical demonstration completed | Final bounded reweighting experiment: 4x START/STAR/STARK/STOPPED negatives plus 1.5x STOP weight. The final board demonstration detected STOP 5/5 and rejected START in the follow-up check; STOT still activated. Epoch 10 cut validation START false activations to 1/182 at V14's threshold, but MSWC STOP recall collapsed to 27.5%. Test unscored. |
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

## Model history and possible future investigation

V13 remains partial and must not be described as a completed 60-epoch run. V14 already used the 1,456-example streaming supplement. V15 established that simply widening the network did not improve the validation tradeoff. V16 established that aggressive hard-negative reweighting reduces START-family false activations only by sacrificing too much STOP recall. Any future model experiment must use a new versioned output folder, preserve the existing split discipline and freeze selection before held-out testing.

## Immediate next step

The end-to-end transport pipeline is documented in `hardware-tests/2026-09-30-v14-streaming.md`; the improved final V16 live behavior is documented in `hardware-tests/2026-09-30-v16-experimental.md`. Further detector development would require a new explicitly authorized experiment. Resource-test samples showed aggregate dual-core CPU near 9.5% for most displayed intervals and a 205,112-byte minimum-free-heap reading, but no uninterrupted final `RESOURCE RESULT` line was captured, so the formal 60-second resource verdict remains unclosed.
