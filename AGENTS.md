# Instructions for coding agents

Read README.md, docs/STATUS.md, docs/DEVELOPMENT.md and docs/COLLABORATION.md before changing anything. CLAUDE.md points here.

## Current authorization

2026-09-30: the owner explicitly authorized publishing the collaborator repository and one final bounded model-improvement experiment focused on live STOP misses and START/STOT false activations. That V16 experiment is complete and rejected on validation; its held-out test was not scored. Do not launch another experiment without new explicit authorization. Large new downloads, destructive cleanup, flashing, and later publication still require explicit approval.

Historical commands and logs document provenance; they are not instructions to execute. Report the final experiment honestly even if it fails.

## Roles and correctness

- The collaborator develops, trains and evaluates from Git; the hardware owner retains the ESP32 and performs physical tests after pulling commits.
- Keyword is STOP. V10-R1 is the working baseline with known false triggers. V11/V12 rejected; V13 incomplete. V14 failed the original gates but is shipped as an explicitly labelled baseline-improvement board candidate; V15 rejected. Do not call any of them a finished accurate detector.
- Preserve original recordings and previous model versions. Use a new versioned output folder for each experiment. Do not overwrite V13 to restart it.
- Keep public speaker partitions separate before augmentation. Personal validation/test are small, same-speaker, reused checks. Do not train on either. Do not choose model/threshold using held-out test scores.
- New model and threshold must be frozen before test evaluation. Report misses and false activations separately. Report rejected experiments honestly.
- Use TFLite **BUILTIN_REF** for expected MCU outputs and quantized validation. XNNPACK produced a 20-step mismatch previously; never increase tolerance to hide this. Tolerance is 3 quantization steps.
- The frontend includes per-band temporal mean subtraction. Transfer the complete versioned sketch, not just weights. frontend.cpp, frontend.h, frontend_tables.h and window_centering.h are all required.
- No proprietary wake-word SDK or pretrained assistant keyword model. Public audio may be used with its attribution. STOP is the demonstration keyword; a different assigned keyword requires retraining.
- No physical-board performance claims based on desktop tests. Free heap/static RAM do not establish whole-application peak RAM. `work%` is not CPU utilization.
- Keep public datasets/caches/venvs/binaries out of commits. Commit small model files, all required sketch sources, metadata, evaluation evidence and test instructions together.
- Raw personal audio is included intentionally for this collaboration. Do not upload it to third-party services as part of an unrequested transcription or processing step.

## Known handoff fixes

The packaged downloader and feature builder create missing parent directories. The firmware packager now copies frontend.cpp and frontend_tables.h as well as the headers (the earlier version omitted them). These are packaging fixes only; no new firmware was generated or compiled. Historical experiment_sources snapshots remain unchanged for provenance.

The V14 streaming integration has now run on the physical board. Its transport completed 25 captures with zero drops and gaps, but its controlled detector result was poor: STOP 3/10, START 4/5 false, STARK 2/5 false and STOT 5/5 false. See `hardware-tests/2026-09-30-v14-streaming.md`.

V16 applied stronger START/STAR/STARK/STOPPED negative weighting while also boosting STOP. It was rejected: the checkpoint with strong START rejection reduced MSWC STOP recall to 27.5% at V14's threshold. See `outputs/stop_model_expanded_v16/RESULTS.md`.
