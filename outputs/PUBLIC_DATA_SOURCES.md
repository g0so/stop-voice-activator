# Expanded STOP training data (V11 experiment)

## Sources and attribution

- **Speech Commands v0.02**, Pete Warden / Google, CC BY 4.0. [Dataset documentation](https://www.tensorflow.org/datasets/catalog/speech_commands), [paper](https://arxiv.org/abs/1804.03209). The full archive contains 105,829 short speech recordings across 35 words; STOP is the positive class. Other words are negative examples. Original archive notices are retained with the extracted data.
- **Multilingual Spoken Words Corpus (English)**, MLCommons contributors, CC BY 4.0. [Publisher documentation](https://mlcommons.org/datasets/multilingual-spoken-words/), [publisher dataset repository](https://huggingface.co/datasets/MLCommons/ml_spoken_words). Selected English training shards 63 and 66 supply STOP and similar-sounding words. Only metadata entries marked VALID with an anonymous speaker ID are selected. Words were extracted automatically from Common Voice; occasional incorrect labels or boundaries remain possible. Actual selected words/counts appear in `dataset/expanded_public/summary.json`.
- **LibriSpeech dev-clean**, Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur, CC BY 4.0. [Publisher documentation](https://www.openslr.org/12). 2,689 sentences remain after excluding transcripts containing STOP or its inflections. Used as longer non-keyword speech; this does not establish performance on all conversational speech.

Download URLs, sizes and publisher checksums are recorded in `expanded_sources.json`. Compressed original sources are retained under `../work/downloads/`. Audio converted for this project is mono, 16 kHz, signed 16-bit PCM.

## Splits and transformations

Public examples are assigned by a deterministic hash of their anonymous speaker ID. No speaker ID within a corpus occurs in more than one train/validation/test partition. Identities across different corpora have not been linked. These are project-specific splits, not the official Speech Commands or LibriSpeech benchmark splits. The Speech Commands hash preserves this project's earlier mini-corpus split.

Training uses gain changes, temporal shifts and background mixing. Augmented copies stay in their source partition. Background source recordings are separated across train/validation/test. The 16 reviewed device recordings remain a small training supplement; the eight local validation and eight local test recordings are reused same-speaker checks, not fresh independent evidence.

The model is trained from random weights with open-source tools. No proprietary voice activation SDK or pretrained assistant-keyword model is used. STOP is a demonstration keyword; a different assigned keyword will require suitable recordings and retraining.

## Evaluation

Model checkpoint and trigger threshold are selected on validation data, using the integer reference runtime. Expanded test scores are computed only after selection is frozen. Individual word error rates and longer-speech false activations must be reported separately. A low clip error rate alone does not demonstrate near-zero false activations during continuous listening.

V11 is an experiment until training and evaluation finish. The previous V10-R1 firmware remains available. Physical ESP32 accuracy, total idle CPU, peak whole-application RAM and remote ASR latency still require measurement.
