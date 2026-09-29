#!/usr/bin/env python3
"""One controlled room-noise fine-tuning experiment; baseline artifacts stay intact."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS', '4')
os.environ.setdefault('TF_NUM_INTEROP_THREADS', '2')
import argparse
import csv
import hashlib
import json
from pathlib import Path
import wave
import numpy as np
import tensorflow as tf
from audio_features import features, read_audio, augment, synthetic_background
from train_keyword import dataset, metrics, quantized_predictions, emit_array

BASE = Path(__file__).resolve().parent
DEST = BASE / 'stop_model_noise_v2'
WORK = BASE.parent / 'work'
SEED = 20260922


def long_audio(path):
    with wave.open(str(path), 'rb') as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        return np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768


def make_data():
    noise_file = BASE / 'fan_noise_new.wav'
    fan = long_audio(noise_file)
    assert len(fan) >= 32000
    fan -= fan.mean()
    rows = list(csv.DictReader((BASE / 'dataset/public/manifest.csv').open()))
    speakers = {s: {r['speaker'] for r in rows if r['split'] == s} for s in ['train','validation','test']}
    assert not (speakers['train'] & speakers['validation'] or speakers['train'] & speakers['test'] or speakers['validation'] & speakers['test'])
    # A spectrum-shaped random noise process for validation. The spectrum is
    # learned from the training noise, so this is not an unseen-noise benchmark.
    noise_segments = np.stack([fan[j:j+16000] for j in range(0, len(fan)-15999, 8000)])
    envelope = np.sqrt(np.mean(np.abs(np.fft.rfft(noise_segments))**2, axis=0))
    data = {}
    for split_index, split in enumerate(['train', 'validation']):
        rng = np.random.default_rng(SEED + split_index)
        def noise():
            if split == 'train':
                start = int(rng.integers(0, len(fan)-16000+1))
                return fan[start:start+16000].copy()
            spec = envelope * np.exp(1j*rng.uniform(0,2*np.pi,len(envelope)))
            spec[0] = 0; spec[-1] = spec[-1].real
            return np.fft.irfft(spec, n=16000).astype(np.float32)
        xs, ys, groups = [], [], []
        subset = [r for r in rows if r['split'] == split]
        for count, row in enumerate(subset):
            a = read_audio(BASE / row['path'])
            y = 2 if row['word'] == 'stop' else 1
            xs.append(features(a)); ys.append(y); groups.append('clean')
            for _ in range(2 if split == 'train' else 1):
                speech = augment(a, rng) if split == 'train' else a.copy()
                speech_rms = max(float(np.sqrt(np.mean(speech**2))), 1e-5)
                # Cover quiet/normal speech, and match the observed fan's level.
                target_rms = 10 ** rng.uniform(-1.9, -1.05)
                speech *= target_rms / speech_rms
                n = noise()
                n *= target_rms / (10**(rng.uniform(-2,22)/20) * max(float(np.sqrt(np.mean(n*n))),1e-6))
                mixed = speech + n
                mixed /= max(1.0, float(np.abs(mixed).max()) / 0.98)
                xs.append(features(mixed)); ys.append(y); groups.append('noisy')
            if (count+1) % 2000 == 0:
                print(f'{split} features {count+1}/{len(subset)}', flush=True)
        for j in range(1600 if split == 'train' else 250):
            n = noise() if j % 2 else synthetic_background(rng)
            if j % 2:
                n *= 10**rng.uniform(-3.3,-1.1) / max(float(np.sqrt(np.mean(n*n))),1e-6)
            xs.append(features(np.clip(n,-1,1))); ys.append(0); groups.append('background')
        data['x_'+split] = np.asarray(xs, np.float32)
        data['y_'+split] = np.asarray(ys, np.int32)
        data['groups_'+split] = np.asarray(groups)
        print(split, 'examples', len(ys), flush=True)
    # Identical public test examples and synthetic-noise test examples to v1.
    with np.load(WORK / 'keyword_features_v1.npz') as original:
        for name in ['x_test','y_test','paths_test']:
            data[name] = original[name]
    np.savez_compressed(WORK / 'room_noise_v2_features.npz', **data)
    return data


def scan_recording(runtime, path, threshold):
    a = long_audio(path)
    xs = np.stack([features(a[j:j+16000]) for j in range(0,len(a)-15999,320)])
    p = quantized_predictions(runtime,xs)[:,2]
    phases = []
    for phase in range(10):
        latched = False; low = 0; last = -100; triggers = []
        for index in range(phase,len(p),10):
            now = index*0.02+0.99
            score = float(p[index])
            low = low+1 if score < .3 else 0
            if latched and low >= 2 and now-last >= 1: latched = False
            if score >= threshold and not latched:
                triggers.append(round(now,2)); latched = True; last = now
        phases.append({'phase_ms':phase*20,'activation_times':triggers})
    return {'max_score':float(p.max()),'threshold':threshold,'phase_results':phases,
            'scores':[{'window_start':round(j*.02,2),'stop_score':float(v)} for j,v in enumerate(p)]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-model',action='store_true')
    args=parser.parse_args()
    DEST.mkdir(exist_ok=True)
    tf.keras.utils.set_random_seed(SEED)
    if args.reuse_model:
        with np.load(WORK/'room_noise_v2_features.npz') as f: data={k:f[k] for k in f.files}
    else:
        data=make_data()
        model=tf.keras.models.load_model(BASE/'stop_model/best.keras')
        model.compile(optimizer=tf.keras.optimizers.Adam(0.0005),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
        counts=np.bincount(data['y_train'],minlength=3)
        weights=(len(data['y_train'])/(3*counts)).astype(np.float32)
        model.fit(dataset(data['x_train'],data['y_train'],True,weights),
                  validation_data=dataset(data['x_validation'],data['y_validation']),epochs=40,verbose=2,
                  callbacks=[tf.keras.callbacks.ModelCheckpoint(DEST/'best.keras',monitor='val_loss',save_best_only=True),
                             tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=9),
                             tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss',patience=4,factor=.5,min_lr=.00003),
                             tf.keras.callbacks.CSVLogger(str(DEST/'training_history.csv'))])
    model=tf.keras.models.load_model(DEST/'best.keras')
    @tf.function(input_signature=[tf.TensorSpec([1,49,24,1],tf.float32)])
    def serving(x): return model(x,training=False)
    from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
    frozen=convert_variables_to_constants_v2(serving.get_concrete_function())
    converter=tf.lite.TFLiteConverter.from_concrete_functions([frozen])
    converter.optimizations=[tf.lite.Optimize.DEFAULT]
    rng=np.random.default_rng(SEED)
    calibration=np.concatenate([rng.choice(np.flatnonzero(data['y_train']==i),150,replace=False) for i in range(3)])
    converter.representative_dataset=lambda:([data['x_train'][i:i+1]] for i in calibration)
    converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type=tf.int8;converter.inference_output_type=tf.int8
    blob=converter.convert();(DEST/'stop_int8.tflite').write_bytes(blob)
    rt=tf.lite.Interpreter(model_content=blob,num_threads=1);rt.allocate_tensors()
    assert not any(t['dtype']==np.float32 for t in rt.get_tensor_details())
    ops=sorted({o['op_name'] for o in rt._get_ops_details() if o['op_name']!='DELEGATE'})
    assert set(ops)<= {'CONV_2D','DEPTHWISE_CONV_2D','FULLY_CONNECTED','RESHAPE','SOFTMAX'}
    valp=quantized_predictions(rt,data['x_validation'])
    candidates=[]
    for threshold in np.arange(1,257)/256:
        passed=True;recalls=[]
        for group in ['clean','noisy']:
            mask=data['groups_validation']==group
            m=metrics(data['y_validation'][mask],valp[mask],threshold)
            passed &= m['other_speech_false_activations']/m['other_speech_total']<=.005
            recalls.append(m['keyword_recall'])
        passed &= not np.any(valp[data['y_validation']==0,2]>=threshold)
        if passed:candidates.append((float(np.mean(recalls)),-float(threshold),float(threshold)))
    threshold=max(candidates)[2]
    testp=quantized_predictions(rt,data['x_test'])
    inp=rt.get_input_details()[0];out=rt.get_output_details()[0]
    summary={'seed':SEED,'model_bytes':len(blob),'parameters':model.count_params(),'operations':ops,
             'threshold':threshold,'input_quantization':list(inp['quantization']),
             'output_quantization':list(out['quantization']),
             'selection':'Validation only. <=0.5% other-word false positives separately for clean and colored-noise validation; zero validation background triggers; maximize mean recall.',
             'test_int8':metrics(data['y_test'],testp,threshold),
             'baseline_test':json.loads((BASE/'stop_model/metrics.json').read_text())['test_int8'],
             'validation':{},'recording_checks':{},
             'noise_sha256':hashlib.sha256((BASE/'fan_noise_new.wav').read_bytes()).hexdigest(),
             'notes':['Same model architecture/frontend; fine-tuned from our own v1 checkpoint.',
                      'Only fan_noise_new.wav is used from personal recordings during training.',
                      'All personal speech clips excluded from training, calibration, checkpoint and threshold selection.',
                      'Validation colored noise uses the training fan spectrum; not unseen-noise evaluation.',
                      'Public test is reused from v1; no new independent final test set.',
                      'Personal speech files are development checks, not accuracy benchmarks.',
                      'Fan replay is a seen-training-noise sanity check, not independent validation.']}
    for group in ['clean','noisy','background']:
        mask=data['groups_validation']==group
        summary['validation'][group]=metrics(data['y_validation'][mask],valp[mask],threshold)
    baseline=tf.lite.Interpreter(model_path=str(BASE/'stop_model/stop_int8.tflite'),num_threads=1);baseline.allocate_tensors()
    for name in ['stop_check_new.wav','stop_check.wav','mic_recheck.wav','fan_noise_new.wav']:
        path=BASE/name
        summary['recording_checks'][name]={'baseline':scan_recording(baseline,path,.90625),
                                         'v2':scan_recording(rt,path,threshold)}
    (DEST/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
    header='#pragma once\n#include <stdint.h>\n'+emit_array('g_stop_model',np.frombuffer(blob,np.uint8),'unsigned char')
    header+=f'const unsigned int g_stop_model_len = {len(blob)};\n'
    (DEST/'stop_model_data.h').write_text(header)
    indexes=[int(np.flatnonzero(data['y_test']==label)[j]) for label in range(3) for j in range(2)]
    qin=np.clip(np.rint(data['x_test'][indexes]/inp['quantization'][0])+inp['quantization'][1],-128,127).astype(np.int8)
    qout=np.rint(testp[indexes]/out['quantization'][0]+out['quantization'][1]).astype(np.int8)
    vh='#pragma once\n#include <stdint.h>\n'+emit_array('g_test_inputs',qin,'int8_t')+emit_array('g_test_outputs',qout,'int8_t')
    vh+='const unsigned int g_test_count = 6;\nconst unsigned int g_input_size = 1176;\n'
    (DEST/'test_vectors.h').write_text(vh)
    print('RESULT',json.dumps({k:v for k,v in summary.items() if k!='recording_checks'},indent=2),flush=True)
    for name,pair in summary['recording_checks'].items():
        print(name,{version:{'max_score':res['max_score'],'activation_counts_by_phase':[len(p['activation_times']) for p in res['phase_results']]} for version,res in pair.items()},flush=True)


if __name__=='__main__':main()
