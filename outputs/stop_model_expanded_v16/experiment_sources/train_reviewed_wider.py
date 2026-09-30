#!/usr/bin/env python3
"""Reviewed restart: select integer checkpoints on validation, then evaluate frozen model once."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','4')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','2')
os.environ.setdefault('OMP_NUM_THREADS','4')
import json,hashlib,shutil,argparse
from pathlib import Path
import numpy as np
import tensorflow as tf
from audio_features import features as raw_features
from train_keyword import quantized_predictions, metrics, emit_array
from train_hard_negatives import crop_start, ds, replay_summary
from retrain_room_noise import long_audio
import retrain_room_noise as replay_module

def normalize(x):
    # Per-window, per-band temporal centering, identically applied on the MCU.
    return (x - x.mean(axis=-3,keepdims=True)).astype(np.float32)

def features(audio):return normalize(raw_features(audio))
replay_module.features=features
scan_recording=replay_module.scan_recording
BASE=Path(__file__).resolve().parent
DEST=BASE/'stop_model_reviewed_v10'
WORK=BASE.parent/'work'
SEED=20261002

def dump(path,obj):path.write_text(json.dumps(obj,indent=2)+'\n')
def rows(manifest,split):
 return [{**r,'path':str(BASE.parent/r['wav']),'wav':Path(r['wav']).name,'class_id':2 if r['word']=='stop' else 1} for r in manifest['recordings'][split]]

def convert(model,xt,calibration):
 @tf.function(input_signature=[tf.TensorSpec([1,49,24,1],tf.float32)])
 def serve(x):return model(x,training=False)
 from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
 cv=tf.lite.TFLiteConverter.from_concrete_functions([convert_variables_to_constants_v2(serve.get_concrete_function())])
 cv.optimizations=[tf.lite.Optimize.DEFAULT]
 cv.representative_dataset=lambda:([xt[i:i+1]] for i in calibration)
 cv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
 cv.inference_input_type=tf.int8;cv.inference_output_type=tf.int8
 return cv.convert()

def runtime(blob):
 rt=tf.lite.Interpreter(model_content=blob,num_threads=1,experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF);rt.allocate_tensors()
 assert not any(t['dtype']==np.float32 for t in rt.get_tensor_details())
 assert {o['op_name'] for o in rt._get_ops_details()}-{'DELEGATE'} <= {'CONV_2D','DEPTHWISE_CONV_2D','RESHAPE','FULLY_CONNECTED','SOFTMAX'}
 return rt

class SaveIntervals(tf.keras.callbacks.Callback):
 def on_epoch_end(self,epoch,logs=None):
  if (epoch+1)%10==0:self.model.save(DEST/f'epoch_{epoch+1:02d}.keras')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--select-only',action='store_true');args=parser.parse_args()
 if args.select_only:
  assert len(list(DEST.glob('*.keras')))==9, 'Expected all nine saved checkpoints'
  assert not (DEST/'frozen_selection.json').exists(), 'Selection already frozen; do not retune'
 else:DEST.mkdir(exist_ok=False)
 tf.keras.utils.set_random_seed(SEED);rng=np.random.default_rng(SEED)
 manifest=json.loads((BASE/'reviewed_restart_manifest.json').read_text());dump(DEST/'dataset_manifest.json',manifest)
 train=rows(manifest,'train');validation=rows(manifest,'validation')
 # Fixed before fitting; test waveforms are not opened until selection succeeds.
 dump(DEST/'experiment_plan.json',{'seed':SEED,'checkpoints':'every 10 epochs and best weighted validation loss, up to 80 epochs','selection':'zero local negative triggers at all 20ms offsets, at least 3/4 local STOP detections at every 200ms phase, >=70% public clean STOP recall, <=1% other-word FP separately clean/noisy, zero validation synthetic background activations; maximize worst-phase local recall then mean local recall then mean public recall then lower threshold','test_access':'only after selection frozen','old_device_recordings':'excluded; random initial weights, wider DS-CNN','frontend':'subtract temporal mean independently for each mel band within every 49-frame window','architecture':'DS-CNN widths 16/24/32; 3-class output','public_replay':'up to 6000 unique examples per class; weight each public class to total 2000'})
 with np.load(WORK/'room_noise_v2_features.npz') as f:
  ids=np.concatenate([rng.choice(np.flatnonzero(f['y_train']==c),min(6000,int(np.sum(f['y_train']==c))),replace=False) for c in range(3)])
  xt=normalize(f['x_train'][ids]);yt=f['y_train'][ids];xv=normalize(f['x_validation']);yv=f['y_validation'];vg=f['groups_validation']
 npublic=len(yt);nval=len(yv);tx=[];ty=[];vx=[];vy=[];crops=[]
 for split,rr in [('train',train),('validation',validation)]:
  for r in rr:
   a=long_audio(Path(r['path']));start=crop_start(a);crops.append({'file':r['path'],'word':r['word'],'split':split,'start_seconds':start/16000,'method':'automatic band-limited energy peak; user confirmed full recording'})
   for n in range(160 if split=='train' else 7):
    if split=='validation':offset=int(np.clip(start+(n-3)*800,0,len(a)-16000))
    elif r['class_id']==1 and n%2==0:offset=int(rng.integers(0,len(a)-16000+1))
    else:offset=int(np.clip(start+rng.integers(-4800,4801),0,len(a)-16000))
    b=a[offset:offset+16000].copy()
    if split=='train':
     b*=10**rng.uniform(-.25,.25)
     if rng.random()<.3:b+=rng.normal(0,rng.uniform(.0001,.001),len(b))
    (tx if split=='train' else vx).append(features(np.clip(b,-1,1)))
    (ty if split=='train' else vy).append(r['class_id'])
 dump(DEST/'crop_annotations.json',crops)
 xt=np.concatenate([xt,np.asarray(tx)]);yt=np.concatenate([yt,ty]).astype(np.int32)
 xv=np.concatenate([xv,np.asarray(vx)]);yv=np.concatenate([yv,vy]).astype(np.int32)
 tw=np.ones(len(yt),np.float32)
 for c in range(3):tw[:npublic][yt[:npublic]==c]=2000/np.sum(yt[:npublic]==c)
 tw[npublic:]=4
 vw=np.ones(len(yv),np.float32);vw[nval:]=25
 model=tf.keras.Sequential([
  tf.keras.layers.Input((49,24,1)),
  tf.keras.layers.Conv2D(16,(5,3),strides=2,padding='same',activation='relu'),
  tf.keras.layers.DepthwiseConv2D(3,strides=2,padding='same',activation='relu'),
  tf.keras.layers.Conv2D(24,1,activation='relu'),
  tf.keras.layers.DepthwiseConv2D(3,strides=(2,1),padding='same',activation='relu'),
  tf.keras.layers.Conv2D(32,1,activation='relu'),
  tf.keras.layers.Flatten(),tf.keras.layers.Dropout(.2),tf.keras.layers.Dense(3,activation='softmax')])
 model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
 if not args.select_only:
  model.fit(ds(xt,yt,tw,True),validation_data=ds(xv,yv,vw),epochs=80,verbose=2,callbacks=[SaveIntervals(),tf.keras.callbacks.ModelCheckpoint(DEST/'best.keras',monitor='val_loss',save_best_only=True),tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss',patience=8,factor=.5,min_lr=.00003),tf.keras.callbacks.CSVLogger(str(DEST/'training_history.csv'))])
 calibration=np.concatenate([rng.choice(np.flatnonzero(yt[:npublic]==c),100,replace=False) for c in range(3)]+[rng.choice(np.arange(npublic,len(yt)),200,replace=False)])
 trials=[];best=None
 for ckpt in sorted(DEST.glob('*.keras')):
  model=tf.keras.models.load_model(ckpt);blob=convert(model,xt,calibration);rt=runtime(blob)
  (DEST/(ckpt.stem+'.tflite')).write_bytes(blob)
  pv=quantized_predictions(rt,xv[:nval]);scans={r['wav']:scan_recording(rt,Path(r['path']),1.) for r in validation}
  scores={k:np.array([s['stop_score'] for s in v['scores']]) for k,v in scans.items()}
  trial={'checkpoint':ckpt.name,'negative_max':max(float(scores[r['wav']].max()) for r in validation if r['class_id']==1),'positive_max':[float(scores[r['wav']].max()) for r in validation if r['class_id']==2],'eligible':[]}
  for threshold in np.arange(1,256)/256:
   if trial['negative_max']>=threshold or np.any(pv[yv[:nval]==0,2]>=threshold):continue
   phase_counts=[sum(scores[r['wav']][phase::10].max()>=threshold for r in validation if r['class_id']==2) for phase in range(10)]
   if min(phase_counts)<3:continue
   pubs=[metrics(yv[:nval][vg==g],pv[vg==g],threshold) for g in ['clean','noisy']]
   if pubs[0]['keyword_recall']<.7 or any(m['other_speech_false_activations']/m['other_speech_total']>.01 for m in pubs):continue
   rank=(int(min(phase_counts)),float(np.mean(phase_counts)),float(np.mean([m['keyword_recall'] for m in pubs])),-float(threshold))
   candidate={'checkpoint':ckpt.name,'threshold':float(threshold),'phase_stop_counts':[int(n) for n in phase_counts],'public_validation':pubs,'rank':rank}
   trial['eligible'].append(candidate)
   if best is None or rank>tuple(best['rank']):best=candidate
  dump(DEST/(ckpt.stem+'_validation.json'),scans);trials.append(trial)
  print('VALIDATION',ckpt.name,'negative max',trial['negative_max'],'positive max',trial['positive_max'],'eligible',len(trial['eligible']),flush=True)
 dump(DEST/'validation_selection.json',trials)
 if best is None:
  dump(DEST/'status.json',{'status':'rejected','reason':'No candidate passes both recall and rejection validation gates. Test audio was not evaluated.'})
  print('REJECTED: test remains untouched.',flush=True);return
 blob=(DEST/(Path(best['checkpoint']).stem+'.tflite')).read_bytes();(DEST/'stop_int8.tflite').write_bytes(blob)
 best['model_sha256']=hashlib.sha256(blob).hexdigest();dump(DEST/'frozen_selection.json',best)
 print('FROZEN',best,flush=True)
 rt=runtime(blob);threshold=best['threshold'];test=rows(manifest,'test')
 checks={r['wav']:scan_recording(rt,Path(r['path']),threshold) for r in test}
 with np.load(WORK/'room_noise_v2_features.npz') as f:xpub=normalize(f['x_test']);ypub=f['y_test']
 pp=quantized_predictions(rt,xpub)
 result={'model_bytes':len(blob),'threshold':threshold,'selection':best,'local_test':{'summary':replay_summary(checks,test),'recordings':checks},'public_regression':metrics(ypub,pp,threshold),'notes':['Eight local test recordings were first evaluated after checkpoint and threshold were frozen.','Same speaker and room; small sample, not a general accuracy or false-activations-per-hour benchmark.','Timing phases reuse recordings and are not independent observations.','Public test is a reused regression set.']}
 dump(DEST/'metrics.json',result)
 (DEST/'stop_model_data.h').write_text('#pragma once\n#include <stdint.h>\n'+emit_array('g_stop_model',np.frombuffer(blob,np.uint8),'unsigned char')+f'const unsigned int g_stop_model_len = {len(blob)};\n')
 inp=rt.get_input_details()[0];out=rt.get_output_details()[0]
 ids=[int(np.flatnonzero(yt==c)[j]) for c in range(3) for j in range(2)]
 xx=xt[ids];pr=quantized_predictions(rt,xx)
 qi=np.clip(np.rint(xx/inp['quantization'][0])+inp['quantization'][1],-128,127).astype(np.int8)
 qo=np.rint(pr/out['quantization'][0]+out['quantization'][1]).astype(np.int8)
 (DEST/'test_vectors.h').write_text('#pragma once\n#include <stdint.h>\n'+emit_array('g_test_inputs',qi,'int8_t')+emit_array('g_test_outputs',qo,'int8_t')+'const unsigned int g_test_count = 6;\nconst unsigned int g_input_size = 1176;\n')
 dump(DEST/'status.json',{'status':'evaluated','physical_board_test':'pending'})
 print('RESULT',result['local_test']['summary'],result['public_regression'],flush=True)

if __name__=='__main__':main()
