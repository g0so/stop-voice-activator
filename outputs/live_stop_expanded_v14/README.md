# STOP detector V14 — baseline-improvement candidate for board test

**Not a pass of the original V11 acceptance gates.** V14 was chosen by an explicit collaborator decision because it clearly beats the deployed V10-R1 on validation false activations while keeping V10's MSWC STOP recall. Full evidence: [../stop_model_expanded_v14/RESULTS.md](../stop_model_expanded_v14/RESULTS.md).

Open `live_stop_expanded_v14.ino` from this folder with all accompanying files (frontend.cpp, frontend.h, frontend_tables.h, window_centering.h, stop_model_data.h, test_vectors.h). Board **ESP32 Dev Module**, ESP32 core **3.3.11**. Wiring unchanged: BCLK 26, WS 33, DIN 32, L/R to GND.

- Model: 13,688 bytes, SHA256 `4be984725547bc3702a6ef3c455a151096eb8138a400fa284b8fb670a5248429`
- Threshold: 0.8671875 (same as V10-R1), 200 ms prediction cadence, same trigger/rearm logic
- Frontend and window centering: byte-identical to V10-R1
- Self-test: 9 reference inputs (V10 had 6), expected outputs from TFLite BUILTIN_REF, tolerance 3 (unchanged)
- **Not compiled yet** on the friend's PC (no Arduino toolchain there). Architecture uses the same five operations as V10 and the same tensor shapes, so the 24 KiB arena is expected to suffice — the startup line reports actual arena use.

## Test plan

1. Upload, open Serial Monitor at 115200, press EN. Save the full startup log.
2. If any line says ERROR, stop and send the log. Do not change threshold or tolerance.
3. After `PASS` and `READY V14`: stay quiet 10 s. Say STOP ten times, 3 s apart.
4. Then START, SHORT, STARK, STOT, **SHOP** five times each, 3 s apart. SHOP and START matter most: on the reused local test recordings V14 triggered on one SHOP recording at 5/10 timing offsets and the START recording at 3/10 (V10 triggered on neither).
5. Repeat the same sequence with V10-R1 (`../live_stop_reviewed_v10/`) in the same place and distance, so the two are directly comparable.
6. Fill in `hardware-tests/TEMPLATE.md` as a new file per model, commit with the serial logs, and push.

`work%` is pipeline wall time, not total CPU. Free heap/static RAM do not establish peak RAM.
