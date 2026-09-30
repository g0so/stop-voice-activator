# Contributing

## Before changing the detector

Read [`AGENTS.md`](AGENTS.md), [`docs/STATUS.md`](docs/STATUS.md) and [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

Preserve V10-R1 and all previous experiment folders. New training runs and firmware candidates must use new versioned directories.

## Pull requests

A firmware or model pull request should include:

- the complete sketch folder rather than a model file alone;
- model SHA256, threshold and preprocessing contract;
- validation results and separate miss/false-activation counts;
- test-access and model-selection notes;
- compilation environment and output;
- known limitations;
- exact board test instructions.

Do not commit public dataset archives, generated feature caches, virtual environments, compiled binaries, model-download caches or real Wi-Fi credentials.

## Model evaluation rules

- Keep public speaker partitions separate before augmentation.
- Do not train on personal validation or test recordings.
- Freeze the model and threshold before held-out test evaluation.
- Use TFLite `BUILTIN_REF` for expected MCU outputs and quantized validation.
- Keep self-test tolerance at three quantization steps.
- Report rejected experiments and regressions.
- Do not turn desktop measurements into physical-board claims.

## Server changes

Run:

```bash
PYTHONPATH=server python3 -m unittest discover -s server/tests -v
python3 -m py_compile server/*.py
```

Protocol changes must update [`docs/PROTOCOL.md`](docs/PROTOCOL.md) and either preserve version-1 compatibility or increment the protocol version.
