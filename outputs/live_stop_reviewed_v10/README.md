# Reviewed STOP detector V10-R1 — runtime reference correction

Open live_stop_reviewed_v10.ino from this folder with all accompanying files. Select ESP32 Dev Module, upload, open Serial Monitor at 115200, then press EN/Reset. Wiring is unchanged: BCLK26, WS33, DIN32, left channel.

Wait for PASS and READY V10-R1. Stay quiet ten seconds, then say STOP ten times with three-second pauses. Next say SHOP, START and SHIT five times each with the same pauses. Share the startup log, detection counts by word, and several status lines. If the self-test reports ERROR, share that message before testing speech.

This folder includes the required new window centering. Do not use just its model header in an old sketch.

Desktop held-out test: all four STOP clips detected, no false triggers on four other-word clips, at all ten timing offsets. This small single-speaker test does not establish broad accuracy. Public regression: 87/101 STOP, 8/677 other-word false activations. Fixed threshold 0.8671875. Model 13,288 bytes.

Compilation passed. Host preprocessing/model parity passed. MCU self-test, inference speed and full memory use still need a board test. Work% is pipeline wall time, not total CPU. No audio streaming is present yet. See ../stop_model_reviewed_v10/RESULTS.md for full results and limits.

R1 corrects the self-test expected outputs to use the non-delegated TFLite reference interpreter. An accelerated-desktop versus reference difference reproduced the reported maximum delta 20. Actual/expected output triples now print for every input. Model, threshold and tolerance 3 are unchanged; physical confirmation is pending. Reload the sketch in Arduino IDE if already open, then re-upload and share the full startup log.
