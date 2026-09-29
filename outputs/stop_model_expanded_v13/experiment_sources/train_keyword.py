#!/usr/bin/env python3
"""Train from scratch; export and evaluate an integer-only STOP detector."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS', '4')
os.environ.setdefault('TF_NUM_INTEROP_THREADS', '2')
os.environ.setdefault('MPLCONFIGDIR', '/tmp/voice-matplotlib')
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import tensorflow as tf
from audio_features import features, read_audio, augment, synthetic_background, FEATURE_SHAPE, WINDOW, MEL_FILTERS

BASE = Path(__file__).resolve().parent
DEST = BASE / 'stop_model'
WORK = BASE.parent / 'work'
CLASS_NAMES = ['background', 'other_speech', 'stop']
SEED = 20260916


def prepare():
    manifest = BASE / 'dataset/public/manifest.csv'
    rows = list(csv.DictReader(manifest.open()))
    speakers = {split: {r['speaker'] for r in rows if r['split'] == split}
                for split in ('train', 'validation', 'test')}
    assert not (speakers['train'] & speakers['test'] or speakers['train'] & speakers['validation']
                or speakers['test'] & speakers['validation'])
    cache = WORK / 'keyword_features_v1.npz'
    fingerprint = hashlib.sha256(manifest.read_bytes() + (BASE/'audio_features.py').read_bytes()).hexdigest()
    if cache.exists():
        with np.load(cache) as stored:
            if str(stored['fingerprint']) == fingerprint:
                print('Loading verified feature cache', flush=True)
                return {k: stored[k] for k in stored.files if k != 'fingerprint'}
    arrays = {}
    for split_index, split in enumerate(('train', 'validation', 'test')):
        rng = np.random.default_rng(SEED + split_index)
        xs, ys, paths = [], [], []
        subset = [r for r in rows if r['split'] == split]
        for index, row in enumerate(subset):
            audio = read_audio(BASE / row['path'])
            label = 2 if row['word'] == 'stop' else 1
            xs.append(features(audio)); ys.append(label); paths.append(row['path'])
            if split == 'train':
                xs.append(features(augment(audio, rng))); ys.append(label); paths.append(row['path'] + '#augmented')
            if (index + 1) % 2000 == 0:
                print(f'{split}: features {index+1}/{len(subset)}', flush=True)
        for i in range(1000 if split == 'train' else 150):
            xs.append(features(synthetic_background(rng))); ys.append(0)
            paths.append(f'synthetic/{split}/{i}')
        arrays[f'x_{split}'] = np.asarray(xs, np.float32)
        arrays[f'y_{split}'] = np.asarray(ys, np.int32)
        arrays[f'paths_{split}'] = np.asarray(paths)
        print(f'{split}: {len(ys)} feature examples; classes {dict(Counter(ys))}', flush=True)
    np.savez_compressed(cache, fingerprint=fingerprint, **arrays)
    return arrays


def make_model():
    return tf.keras.Sequential([
        tf.keras.layers.Input(shape=FEATURE_SHAPE),
        tf.keras.layers.Conv2D(8, (5, 3), strides=(2, 2), padding='same', activation='relu'),
        tf.keras.layers.DepthwiseConv2D(3, strides=2, padding='same', activation='relu'),
        tf.keras.layers.Conv2D(16, 1, activation='relu'),
        tf.keras.layers.DepthwiseConv2D(3, strides=(2, 1), padding='same', activation='relu'),
        tf.keras.layers.Conv2D(24, 1, activation='relu'),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dropout(0.20),
        tf.keras.layers.Dense(3, activation='softmax')], name='stop_tiny_dscnn')


def dataset(x, y, training=False, weights=None):
    if weights is None:
        ds = tf.data.Dataset.from_tensor_slices((x, y))
    else:
        ds = tf.data.Dataset.from_tensor_slices((x, y, weights[y]))
    if training:
        ds = ds.shuffle(len(y), seed=SEED, reshuffle_each_iteration=True)
    opts = tf.data.Options()
    opts.threading.private_threadpool_size = 2
    return ds.batch(64).with_options(opts).prefetch(1)


def quantized_predictions(interpreter, x):
    inp, out = interpreter.get_input_details()[0], interpreter.get_output_details()[0]
    scale, zero = inp['quantization']
    oscale, ozero = out['quantization']
    probs = []
    for example in x:
        quantized = np.clip(np.rint(example / scale) + zero, -128, 127).astype(np.int8)[None]
        interpreter.set_tensor(inp['index'], quantized)
        interpreter.invoke()
        probs.append((interpreter.get_tensor(out['index'])[0].astype(np.float32) - ozero) * oscale)
    return np.array(probs)


def metrics(y, probs, threshold):
    prediction = probs.argmax(axis=1)
    matrix = np.zeros((3, 3), dtype=int)
    for truth, guess in zip(y, prediction): matrix[truth, guess] += 1
    positive = y == 2
    fired = probs[:, 2] >= threshold
    tp, fn = int(np.sum(fired & positive)), int(np.sum(~fired & positive))
    other = y == 1
    bg = y == 0
    fp = int(np.sum(fired & ~positive))
    return {'accuracy': float(np.mean(prediction == y)), 'confusion_matrix': matrix.tolist(),
            'keyword_detected': tp, 'keyword_total': int(positive.sum()), 'keyword_missed': fn,
            'keyword_recall': tp / max(1, int(positive.sum())), 'keyword_precision': tp/max(1, tp+fp),
            'other_speech_false_activations': int(np.sum(fired & other)),
            'other_speech_total': int(other.sum()),
            'synthetic_background_false_activations': int(np.sum(fired & bg)),
            'synthetic_background_total': int(bg.sum())}


def emit_array(name, data, ctype):
    flat = np.asarray(data).flatten()
    lines = [', '.join(str(int(v)) for v in flat[i:i+16]) for i in range(0, len(flat), 16)]
    return f'alignas(16) const {ctype} {name}[] = {{\n  ' + ',\n  '.join(lines) + '\n};\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, default=40)
    parser.add_argument('--reuse-model', action='store_true')
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True); WORK.mkdir(exist_ok=True)
    tf.keras.utils.set_random_seed(SEED)
    data = prepare()
    best = DEST / 'best.keras'
    if not args.reuse_model:
        model = make_model()
        model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss='sparse_categorical_crossentropy', metrics=['accuracy'])
        model.summary()
        counts = np.bincount(data['y_train'], minlength=3)
        weights = (len(data['y_train']) / (3 * counts)).astype(np.float32)
        callbacks = [tf.keras.callbacks.ModelCheckpoint(best, monitor='val_loss', save_best_only=True),
                     tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=9, restore_best_weights=True),
                     tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss', patience=4, factor=0.5, min_lr=0.00005),
                     tf.keras.callbacks.CSVLogger(str(DEST/'training_history.csv'))]
        model.fit(dataset(data['x_train'], data['y_train'], True, weights),
                  validation_data=dataset(data['x_validation'], data['y_validation']),
                  epochs=args.epochs, callbacks=callbacks, verbose=2)
    model = tf.keras.models.load_model(best)
    print('Converting best checkpoint to integer-only TFLite', flush=True)
    # Freeze deployment batch size to one so Flatten needs no dynamic SHAPE/PACK ops.
    @tf.function(input_signature=[tf.TensorSpec([1, *FEATURE_SHAPE], tf.float32, name='features')])
    def serving(x):
        return {'scores': model(x, training=False)}
    from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
    frozen = convert_variables_to_constants_v2(serving.get_concrete_function())
    converter = tf.lite.TFLiteConverter.from_concrete_functions([frozen])
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    rng = np.random.default_rng(SEED)
    calibration = np.concatenate([rng.choice(np.flatnonzero(data['y_train'] == i), 100, replace=False) for i in range(3)])
    converter.representative_dataset = lambda: ([data['x_train'][i:i+1]] for i in calibration)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    blob = converter.convert()
    (DEST/'stop_int8.tflite').write_bytes(blob)
    runtime = tf.lite.Interpreter(model_content=blob, num_threads=1)
    runtime.allocate_tensors()
    inp, out = runtime.get_input_details()[0], runtime.get_output_details()[0]
    assert inp['dtype'] == np.int8 and out['dtype'] == np.int8
    assert not any(t['dtype'] == np.float32 for t in runtime.get_tensor_details())
    operations = sorted({o['op_name'] for o in runtime._get_ops_details() if o['op_name'] != 'DELEGATE'})
    supported = {'CONV_2D', 'DEPTHWISE_CONV_2D', 'RESHAPE', 'FULLY_CONNECTED', 'SOFTMAX'}
    if not set(operations) <= supported:
        raise RuntimeError(f'Unexpected model operations: {operations}')
    val_probs = quantized_predictions(runtime, data['x_validation'])
    # Choose a threshold solely on validation: <=0.5% other-word false triggers,
    # no synthetic background triggers, then maximize keyword recall.
    candidates = []
    for threshold in np.arange(1, 257) / 256:
        result = metrics(data['y_validation'], val_probs, threshold)
        if (result['other_speech_false_activations'] / result['other_speech_total'] <= 0.005
                and result['synthetic_background_false_activations'] == 0):
            candidates.append((result['keyword_recall'], -float(threshold), float(threshold)))
    threshold = max(candidates)[2]
    print(f'Validation-selected threshold: {threshold}', flush=True)
    test_probs = quantized_predictions(runtime, data['x_test'])
    float_probs = model.predict(dataset(data['x_test'], data['y_test']), verbose=0)
    result = {'keyword': 'stop', 'classes': CLASS_NAMES, 'seed': SEED,
              'model_bytes': len(blob), 'parameters': model.count_params(), 'operations': operations,
              'input_shape': inp['shape'].tolist(), 'input_quantization': list(inp['quantization']),
              'output_quantization': list(out['quantization']), 'threshold': threshold,
              'threshold_policy': 'Validation only: other-word clip FPR <=0.5%, zero synthetic background triggers; maximize recall then minimize threshold.',
              'validation_int8': metrics(data['y_validation'], val_probs, threshold),
              'test_int8': metrics(data['y_test'], test_probs, threshold),
              'test_float_at_same_threshold': metrics(data['y_test'], float_probs, threshold),
              'mean_absolute_probability_quantization_change': float(np.mean(np.abs(test_probs-float_probs))),
              'tensorflow_version': tf.__version__,
              'limitations': ['Isolated one-second clips, not continuous wake-word evaluation.',
                              'Background examples are synthetic; real ambient audio is not evaluated.',
                              'RAM, idle CPU and end-to-end latency are unmeasured on hardware.',
                              'Only stop is trained. Rocket recordings are excluded.']}
    (DEST/'metrics.json').write_text(json.dumps(result, indent=2)+'\n')
    with (DEST/'test_predictions.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['path', 'true_class', 'p_background', 'p_other_speech', 'p_stop', 'activated'])
        for path, label, probs in zip(data['paths_test'], data['y_test'], test_probs):
            writer.writerow([path, CLASS_NAMES[label], *map(float, probs), bool(probs[2]>=threshold)])
    header = '#pragma once\n#include <stdint.h>\n' + emit_array('g_stop_model', np.frombuffer(blob, dtype=np.uint8), 'unsigned char')
    header += f'const unsigned int g_stop_model_len = {len(blob)};\n'
    (DEST/'stop_model_data.h').write_text(header)
    frontend = {'sample_rate':16000, 'clip_samples':16000, 'frame_samples':480, 'hop_samples':320,
                'fft_size':512, 'mel_bins':24, 'mel_low_hz':80, 'mel_high_hz':7600,
                'input_shape':[49,24,1], 'pcm_scale':32768,
                'processing':'Subtract each frame mean; symmetric Hann(480); zero-pad to 512; power=abs(rfft)^2/512; area-normalized triangular mel filters; 10*log10(max(energy,1e-10)); clip [-80,0] dB; normalize (dB+40)/40.',
                'padding':'Right-pad clips shorter than 16000 with zeros; do not normalize each clip by its peak.'}
    (DEST/'frontend.json').write_text(json.dumps(frontend, indent=2)+'\n')
    np.savez(DEST/'frontend_constants.npz', window=WINDOW, mel_filters=MEL_FILTERS)
    # Known inputs/outputs let the next step check the microcontroller runtime.
    indexes = [int(np.flatnonzero(data['y_test']==label)[i]) for label in range(3) for i in range(2)]
    vectors = data['x_test'][indexes]
    scale, zero = inp['quantization']
    qvectors = np.clip(np.rint(vectors/scale)+zero,-128,127).astype(np.int8)
    qoutputs = np.rint(test_probs[indexes]/out['quantization'][0]+out['quantization'][1]).astype(np.int8)
    np.savez(DEST/'test_vectors.npz', inputs=qvectors, outputs=qoutputs, labels=data['y_test'][indexes])
    vector_header = '#pragma once\n#include <stdint.h>\n' + emit_array('g_test_inputs', qvectors, 'int8_t')
    vector_header += emit_array('g_test_outputs', qoutputs, 'int8_t')
    vector_header += 'const unsigned int g_test_count = 6;\nconst unsigned int g_input_size = 1176;\n'
    (DEST/'test_vectors.h').write_text(vector_header)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
