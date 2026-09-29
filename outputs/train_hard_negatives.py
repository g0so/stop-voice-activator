#!/usr/bin/env python3
"""Hard-negative adaptation experiment. The eight-file evaluation is now a reused development check."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','4')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','2')
os.environ.setdefault('OMP_NUM_THREADS','4')
import csv, hashlib, json, wave
from pathlib import Path
import numpy as np
import tensorflow as tf
from scipy.signal import butter, sosfiltfilt
from audio_features import features
from train_keyword import quantized_predictions, metrics, emit_array
from retrain_room_noise import long_audio, scan_recording

BASE=Path(__file__).resolve().parent
WORK=BASE.parent/'work'
DEST=BASE/'stop_model_hardneg_v4'
SEED=20260924
TRAIN=BASE/'dataset/device_adaptation/train/s01/20260922T050633_a27f8c79'
TEST=BASE/'dataset/device_adaptation/test/s01/20260922T051240_caada027'
VALIDATION_INDEXES={9,17,2,6}  # STOP validation retained; hello/rocket reserved, shop/start now train.


def inventory(folder, expected):
    rows=[]
    for path in sorted(folder.glob('*.json')):
        if path.name=='session_summary.json':continue
        m=json.loads(path.read_text())
        if not m.get('accepted'):continue
        wav=folder/m['wav']
        with wave.open(str(wav),'rb') as w:
            assert (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes())==(16000,1,2,80000)
            raw=w.readframes(80000)
        m['path']=str(wav);m['sha256']=hashlib.sha256(raw).hexdigest()
        m['class_id']=2 if m['label']=='stop' else 1
        m['clipped']=int(np.sum(np.abs(np.frombuffer(raw,dtype='<i2').astype(np.int32))>=32767))
        rows.append(m)
    assert len(rows)==expected
    assert len({r['prompt_index'] for r in rows})==expected
    return rows


def crop_start(audio):
    # Automatic provisional speech localization, using no model predictions.
    band=sosfiltfilt(butter(4,[300,3500],btype='bandpass',fs=16000,output='sos'),audio)
    energy=np.convolve(band*band,np.ones(3200)/3200,mode='same')
    # Prompts ask for silence first, then a single utterance, then silence.
    peak=8000+int(np.argmax(energy[8000:56000]))
    return int(np.clip(peak-8000,0,len(audio)-16000))


def ds(x,y,weights,shuffle=False):
    d=tf.data.Dataset.from_tensor_slices((x,y,weights.astype(np.float32)))
    if shuffle:d=d.shuffle(len(y),seed=SEED,reshuffle_each_iteration=True)
    opts=tf.data.Options();opts.threading.private_threadpool_size=2
    return d.batch(64).with_options(opts).prefetch(1)


def replay_summary(checks, rows):
    phases=[]
    for phase in range(10):
        tp=fp=duplicates=0
        for r in rows:
            count=len(checks[r['wav']]['phase_results'][phase]['activation_times'])
            if r['class_id']==2:tp+=int(count>0);duplicates+=max(0,count-1)
            else:fp+=int(count>0)
        phases.append({'phase_ms':phase*20,'stop_clips_detected':tp,'negative_clips_triggered':fp,'extra_positive_triggers':duplicates})
    return {'positive_clips':sum(r['class_id']==2 for r in rows),
            'negative_clips':sum(r['class_id']==1 for r in rows),'phase_results':phases}


def main():
    DEST.mkdir(exist_ok=True);tf.keras.utils.set_random_seed(SEED)
    train=inventory(TRAIN,20);test=inventory(TEST,8)
    assert not ({r['sha256'] for r in train}&{r['sha256'] for r in test})
    assert len({r['sha256'] for r in train+test})==28
    (DEST/'recording_inventory.json').write_text(json.dumps({'train':train,'test':test},indent=2)+'\n')
    rng=np.random.default_rng(SEED)
    with np.load(WORK/'room_noise_v2_features.npz') as f:
        indexes=np.concatenate([rng.choice(np.flatnonzero(f['y_train']==c),2000,replace=np.sum(f['y_train']==c)<2000) for c in range(3)])
        xt=f['x_train'][indexes];yt=f['y_train'][indexes]
        xv=f['x_validation'];yv=f['y_validation'];vg=f['groups_validation']
        xpubtest=f['x_test'];ypubtest=f['y_test']
    tx=[];ty=[];vx=[];vy=[];crops=[]
    for r in train:
        audio=long_audio(Path(r['path']));start=crop_start(audio)
        val=r['prompt_index'] in VALIDATION_INDEXES
        crops.append({'wav':r['wav'],'prompt':r['prompt'],'start_seconds':start/16000,'end_seconds':start/16000+1,
                      'role':'validation' if val else 'training','method':'Highest 200ms band-limited energy; provisional automatic annotation'})
        for n in range(5 if val else (100 if r['prompt'] in {'shop','start','stock','top'} else 40)):
            shift=int((n-2)*800) if val else int(rng.integers(-2400,2401))
            offset=int(np.clip(start+shift,0,len(audio)-16000));a=audio[offset:offset+16000].copy()
            if not val:
                a*=10**rng.uniform(-.18,.18)
                if rng.random()<.4:a+=rng.normal(0,rng.uniform(.0001,.0015),len(a))
            (vx if val else tx).append(features(np.clip(a,-1,1)))
            (vy if val else ty).append(r['class_id'])
    (DEST/'crop_annotations.json').write_text(json.dumps(crops,indent=2)+'\n')
    print('Device crop windows:',json.dumps(crops),flush=True)
    npublic=len(yt);nval=len(yv)
    xt=np.concatenate([xt,np.asarray(tx)]);yt=np.concatenate([yt,ty]).astype(np.int32)
    xv=np.concatenate([xv,np.asarray(vx)]);yv=np.concatenate([yv,vy]).astype(np.int32)
    tw=np.ones(len(yt),np.float32);tw[npublic:]=4.0
    vw=np.ones(len(yv),np.float32);vw[nval:]=40.0
    model=tf.keras.models.load_model(BASE/'stop_model_noise_v2/best.keras')
    model.compile(optimizer=tf.keras.optimizers.Adam(.0002),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
    model.fit(ds(xt,yt,tw,True),validation_data=ds(xv,yv,vw),epochs=40,verbose=2,
              callbacks=[tf.keras.callbacks.ModelCheckpoint(DEST/'best.keras',monitor='val_loss',save_best_only=True),
                         tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=10),
                         tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss',patience=4,factor=.5,min_lr=.000025),
                         tf.keras.callbacks.CSVLogger(str(DEST/'training_history.csv'))])
    model=tf.keras.models.load_model(DEST/'best.keras')
    @tf.function(input_signature=[tf.TensorSpec([1,49,24,1],tf.float32)])
    def serve(x):return model(x,training=False)
    from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
    converter=tf.lite.TFLiteConverter.from_concrete_functions([convert_variables_to_constants_v2(serve.get_concrete_function())])
    converter.optimizations=[tf.lite.Optimize.DEFAULT]
    calibration=np.concatenate([rng.choice(np.flatnonzero(yt[:npublic]==c),100,replace=False) for c in range(3)]+[rng.choice(np.arange(npublic,len(yt)),150,replace=False)])
    converter.representative_dataset=lambda:([xt[i:i+1]] for i in calibration)
    converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type=tf.int8;converter.inference_output_type=tf.int8
    blob=converter.convert();(DEST/'stop_int8.tflite').write_bytes(blob)
    rt=tf.lite.Interpreter(model_content=blob,num_threads=1);rt.allocate_tensors()
    assert not any(t['dtype']==np.float32 for t in rt.get_tensor_details())
    ops=sorted({r['op_name'] for r in rt._get_ops_details() if r['op_name']!='DELEGATE'})
    assert set(ops)<={'CONV_2D','DEPTHWISE_CONV_2D','RESHAPE','FULLY_CONNECTED','SOFTMAX'}
    pval=quantized_predictions(rt,xv[:nval])
    valrows=[r for r in train if r['prompt_index'] in VALIDATION_INDEXES]
    device_val={r['wav']:scan_recording(rt,Path(r['path']),1.0) for r in valrows}
    candidates=[]
    for threshold in np.arange(1,257)/256:
        ok=True;recalls=[]
        for group in ['clean','noisy']:
            mask=vg==group;m=metrics(yv[:nval][mask],pval[mask],threshold)
            ok &= m['other_speech_false_activations']/m['other_speech_total']<=.005
            recalls.append(m['keyword_recall'])
        ok &= not np.any(pval[yv[:nval]==0,2]>=threshold)
        positive_rates=[]
        for r in valrows:
            scores=np.asarray([s['stop_score'] for s in device_val[r['wav']]['scores']])
            if r['class_id']==1:ok &= scores.max()<threshold
            else:positive_rates.append(np.mean([scores[phase::10].max()>=threshold for phase in range(10)]))
        if ok:candidates.append((float(np.mean(positive_rates)),float(np.mean(recalls)),-float(threshold),float(threshold)))
    threshold=max(candidates)[3]
    selection={'threshold':threshold,'rule':'Validation only; no triggers on two local negative validation recordings at any scanned alignment; <=0.5% public other-speech false positives separately clean/noisy; zero public validation background triggers. Maximize local positive detection across timing phases, then public recall, then use lowest threshold.',
               'device_validation_indexes':sorted(VALIDATION_INDEXES),'model_sha256':hashlib.sha256(blob).hexdigest()}
    # Persist final selection BEFORE evaluating held-out test audio features.
    (DEST/'frozen_selection.json').write_text(json.dumps(selection,indent=2)+'\n')
    print('Frozen selection:',selection,flush=True)
    ptest=quantized_predictions(rt,xpubtest)
    comparison={}
    for name,model_path,t in [('baseline',BASE/'stop_model/stop_int8.tflite',.90625),
                              ('noise_v2',BASE/'stop_model_noise_v2/stop_int8.tflite',.97265625),
                              ('hardneg_v4',DEST/'stop_int8.tflite',threshold)]:
        runtime=tf.lite.Interpreter(model_path=str(model_path),num_threads=1);runtime.allocate_tensors()
        checks={r['wav']:scan_recording(runtime,Path(r['path']),t) for r in test}
        comparison[name]={'summary':replay_summary(checks,test),'recordings':checks}
    inp=rt.get_input_details()[0];out=rt.get_output_details()[0]
    result={'seed':SEED,'model_bytes':len(blob),'parameters':model.count_params(),'operations':ops,
            'input_quantization':list(inp['quantization']),'output_quantization':list(out['quantization']),
            **selection,'test_public':metrics(ypubtest,ptest,threshold),'local_test':comparison,
            'notes':['16 original device clips for gradients; 4 from training batch reserved for selection. Shop/start/top/stock emphasized.',
                     'Eight evaluation clips excluded from training, calibration, checkpoint and numeric threshold selection, but their v3 failure patterns informed this experiment. They are now reused development checks, not an untouched test.',
                     'One speaker and room; eight recordings are a small sanity test, not general accuracy.',
                     'Public test set is reused; not a fresh final evaluation.',
                     'Crop locations are automatic; prompt labels were not independently transcribed.',
                     'Timing phase runs reuse each recording and are not independent samples.']}
    (DEST/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
    header='#pragma once\n#include <stdint.h>\n'+emit_array('g_stop_model',np.frombuffer(blob,np.uint8),'unsigned char')
    header+=f'const unsigned int g_stop_model_len = {len(blob)};\n'
    (DEST/'stop_model_data.h').write_text(header)
    ids=[int(np.flatnonzero(ypubtest==c)[j]) for c in range(3) for j in range(2)]
    qin=np.clip(np.rint(xpubtest[ids]/inp['quantization'][0])+inp['quantization'][1],-128,127).astype(np.int8)
    qout=np.rint(ptest[ids]/out['quantization'][0]+out['quantization'][1]).astype(np.int8)
    vh='#pragma once\n#include <stdint.h>\n'+emit_array('g_test_inputs',qin,'int8_t')+emit_array('g_test_outputs',qout,'int8_t')
    vh+='const unsigned int g_test_count = 6;\nconst unsigned int g_input_size = 1176;\n'
    (DEST/'test_vectors.h').write_text(vh)
    print('PUBLIC TEST',json.dumps(result['test_public']),flush=True)
    print('LOCAL TEST',json.dumps({k:v['summary'] for k,v in comparison.items()},indent=2),flush=True)


if __name__=='__main__':main()
