#!/usr/bin/env python3
"""Train a public-data-first STOP model; freeze selection before expanded test evaluation."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2');os.environ.setdefault('TF_NUM_INTRAOP_THREADS','4');os.environ.setdefault('TF_NUM_INTEROP_THREADS','2');os.environ.setdefault('OMP_NUM_THREADS','4')
import argparse,csv,json,hashlib,shutil,sys
from pathlib import Path
import numpy as np
import tensorflow as tf
from train_keyword import quantized_predictions,metrics,emit_array
from train_reviewed_wider import convert,runtime,scan_recording,rows
from train_hard_negatives import replay_summary
BASE=Path(__file__).resolve().parent;CACHE=BASE.parent/'work/expanded_features_v11';DEST=BASE/'stop_model_expanded_v11';SEED=2026092911

def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def dataset(x,y,w,shuffle=False):
 d=tf.data.Dataset.from_tensor_slices((x,y,w.astype(np.float32)))
 if shuffle:d=d.shuffle(len(y),seed=SEED,reshuffle_each_iteration=True)
 opts=tf.data.Options();opts.threading.private_threadpool_size=2
 return d.batch(128).with_options(opts).prefetch(1)
class Checkpoints(tf.keras.callbacks.Callback):
 def on_epoch_end(self,epoch,logs=None):
  if (epoch+1)%10==0:self.model.save(DEST/f'epoch_{epoch+1:02d}.keras')

def breakdown(y,p,rr,threshold):
 out={}
 for source in sorted({r['source'] for r in rr}):
  mask=np.asarray([r['source']==source for r in rr]);out[source]=metrics(y[mask],p[mask],threshold)
 return out

def main():
 global DEST
 parser=argparse.ArgumentParser();parser.add_argument('--select-only',action='store_true');parser.add_argument('--output-dir',default='stop_model_expanded_v11');parser.add_argument('--warmstart');parser.add_argument('--batchnorm',action='store_true');parser.add_argument('--epochs',type=int,default=60);parser.add_argument('--streaming-supplement',action='store_true',help='Append work/streaming_supplement (training recordings only) to the training set');parser.add_argument('--widths',default='16,24,32',help='DS-CNN channel widths for the batch-normalized architecture');parser.add_argument('--hard-negative-words',default='',help='Comma-separated MSWC words receiving extra training weight');parser.add_argument('--hard-negative-weight',type=float,default=1.0);parser.add_argument('--keyword-weight',type=float,default=1.0,help='Additional multiplier for STOP examples');parser.add_argument('--critical-words',default='short,start,stark,shop',help='Comma-separated MSWC words gated separately during selection');args=parser.parse_args();W=[int(w) for w in args.widths.split(',')];assert len(W)==3 and (args.batchnorm or W==[16,24,32]),'--widths applies to --batchnorm';assert args.hard_negative_weight>=1 and args.keyword_weight>=1;hard_words={w.strip().lower() for w in args.hard_negative_words.split(',') if w.strip()};critical_words=[w.strip().lower() for w in args.critical_words.split(',') if w.strip()];DEST=BASE/args.output_dir
 if args.select_only:
  assert (DEST/'best.keras').exists() and not (DEST/'frozen_selection.json').exists()
 else:DEST.mkdir(exist_ok=False)
 if not args.select_only:
  source_dir=DEST/'experiment_sources';source_dir.mkdir()
  for name in ['train_expanded_keyword.py','build_expanded_features.py','prepare_expanded_audio.py','audio_features.py','train_reviewed_wider.py','train_keyword.py','retrain_room_noise.py']+(['build_streaming_supplement.py'] if args.streaming_supplement else []):
   shutil.copy2(BASE/name,source_dir/name)
  dump(DEST/'software_versions.json',{'python':sys.version,'tensorflow':tf.__version__,'numpy':np.__version__})
 tf.keras.utils.set_random_seed(SEED);rng=np.random.default_rng(SEED)
 summary=json.loads((CACHE/'summary.json').read_text());dump(DEST/'dataset_summary.json',summary)
 local_manifest=json.loads((BASE/'reviewed_restart_manifest.json').read_text());local_val=rows(local_manifest,'validation')
 # Test is excluded from selection, including the old local test which is now a reused check.
 plan={'seed':SEED,'epochs':args.epochs,'shuffle':'Full training dataset each epoch; source/word order cannot survive a small shuffle buffer','warmstart':args.warmstart,'batchnorm':args.batchnorm,'early_stopping':'Stop after 12 epochs without validation-loss improvement','architecture':f'DS-CNN {W[0]}/{W[1]}/{W[2]}, temporal-mean-centered 49x24 log-mel'+(', same as V10' if W==[16,24,32] else ', wider than V10'),'loss':'sparse categorical crossentropy; class-balanced sample weights; MSWC negatives weighted x2; reviewed-device examples have absolute sample weight 8','hard_negative_words':sorted(hard_words),'hard_negative_weight':args.hard_negative_weight,'keyword_weight':args.keyword_weight,'critical_words':critical_words,'selection':'At least 80% SC STOP recall, <=0.5% SC other-word FP, at least 70% MSWC STOP recall, <=1% MSWC other-word FP, <=5% FP separately for each configured critical word (zero when fewer than 20 validation clips), <=0.5% sampled continuous-negative window FP, zero validation background triggers, >=3/4 local STOP at every prediction phase and zero local negative triggers. Maximize minimum local phase detection, then average SC/MSWC recall, then lower threshold.','test':'Expanded public test loaded only after model and threshold frozen; reviewed local test is reused development data','runtime':'TFLite BUILTIN_REF, no desktop accelerator delegates','streaming_supplement':'Training-only rolling negatives/augmented positives from the 16 reviewed training recordings, sample weight 8' if args.streaming_supplement else None}
 dump(DEST/'experiment_plan.json',plan)
 xt=np.load(CACHE/'x_train.npy',mmap_mode='r');yt=np.load(CACHE/'y_train.npy');tr=json.loads((CACHE/'rows_train.json').read_text())
 if args.streaming_supplement:
  supplement=BASE.parent/'work/streaming_supplement';sr=json.loads((supplement/'rows.json').read_text())
  assert all(r['split']=='train' for r in sr),'Supplement must come from training recordings only'
  xt=np.concatenate([xt,np.load(supplement/'x.npy')]);yt=np.concatenate([yt,np.load(supplement/'y.npy')]).astype(np.int32);tr=tr+sr
 xv=np.load(CACHE/'x_validation.npy',mmap_mode='r');yv=np.load(CACHE/'y_validation.npy');vr=json.loads((CACHE/'rows_validation.json').read_text())
 weights=np.ones(len(yt),np.float32)
 for c in range(3):weights[yt==c]=len(yt)/(3*np.sum(yt==c))
 for i,r in enumerate(tr):
  if r['source']=='mswc' and r['label']==1:weights[i]*=2
  if r['source']=='mswc' and r['label']==1 and r.get('word','').lower() in hard_words:weights[i]*=args.hard_negative_weight
  if r['source']=='reviewed_device':weights[i]=8.
 weights[yt==2]*=args.keyword_weight
 vw=np.ones(len(yv),np.float32)
 for c in range(3):vw[yv==c]=len(yv)/(3*np.sum(yv==c))
 for i,r in enumerate(vr):
  if r['source']=='mswc':vw[i]*=2
  if r['source']=='mswc' and r['label']==1 and r.get('word','').lower() in hard_words:vw[i]*=min(args.hard_negative_weight,4.)
  if r['source']=='reviewed_device':vw[i]*=10
 vw[yv==2]*=args.keyword_weight
 if not args.select_only:
  model=tf.keras.Sequential([tf.keras.layers.Input((49,24,1)),tf.keras.layers.Conv2D(16,(5,3),strides=2,padding='same',activation='relu'),tf.keras.layers.DepthwiseConv2D(3,strides=2,padding='same',activation='relu'),tf.keras.layers.Conv2D(24,1,activation='relu'),tf.keras.layers.DepthwiseConv2D(3,strides=(2,1),padding='same',activation='relu'),tf.keras.layers.Conv2D(32,1,activation='relu'),tf.keras.layers.Flatten(),tf.keras.layers.Dropout(.2),tf.keras.layers.Dense(3,activation='softmax')])
  if args.batchnorm:
   assert not args.warmstart,'Batch-normalized architecture starts from random weights'
   L=tf.keras.layers
   model=tf.keras.Sequential([L.Input((49,24,1)),
    L.Conv2D(W[0],(5,3),strides=2,padding='same',use_bias=False),L.BatchNormalization(),L.ReLU(),
    L.DepthwiseConv2D(3,strides=2,padding='same',use_bias=False),L.BatchNormalization(),L.ReLU(),
    L.Conv2D(W[1],1,use_bias=False),L.BatchNormalization(),L.ReLU(),
    L.DepthwiseConv2D(3,strides=(2,1),padding='same',use_bias=False),L.BatchNormalization(),L.ReLU(),
    L.Conv2D(W[2],1,use_bias=False),L.BatchNormalization(),L.ReLU(),
    L.Flatten(),L.Dropout(.2),L.Dense(3,activation='softmax')])
  if args.warmstart:model=tf.keras.models.load_model(BASE/args.warmstart)
  model.compile(optimizer=tf.keras.optimizers.Adam(.0003 if args.warmstart else .001),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
  model.fit(dataset(xt,yt,weights,True),validation_data=dataset(xv,yv,vw),epochs=args.epochs,verbose=2,callbacks=[Checkpoints(),tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=12),tf.keras.callbacks.ModelCheckpoint(DEST/'best.keras',monitor='val_loss',save_best_only=True),tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss',patience=6,factor=.5,min_lr=.00003),tf.keras.callbacks.CSVLogger(str(DEST/'training_history.csv'))])
 calibration=np.concatenate([rng.choice(np.flatnonzero(yt==c),200,replace=False) for c in range(3)])
 trials=[];best=None
 critical_masks={word:np.asarray([r['source']=='mswc' and r['word']==word for r in vr]) for word in critical_words}
 for checkpoint in sorted(DEST.glob('*.keras')):
  model=tf.keras.models.load_model(checkpoint);blob=convert(model,xt,calibration);(DEST/(checkpoint.stem+'.tflite')).write_bytes(blob);rt=runtime(blob)
  pv=quantized_predictions(rt,xv);np.save(DEST/(checkpoint.stem+'_validation_predictions.npy'),pv)
  scans={r['wav']:scan_recording(rt,Path(r['path']),1.) for r in local_val};scores={k:np.asarray([s['stop_score'] for s in v['scores']]) for k,v in scans.items()}
  trial={'checkpoint':checkpoint.name,'eligible':[],'diagnostics':[]};dump(DEST/(checkpoint.stem+'_local_validation.json'),scans)
  for threshold in np.arange(128,256)/256:
   b=breakdown(yv,pv,vr,threshold)
   sc=b['speech_commands_v002'];ms=b['mswc'];long=b['librispeech_dev_clean']
   counts=[sum(scores[r['wav']][phase::10].max()>=threshold for r in local_val if r['class_id']==2) for phase in range(10)]
   local_fp=sum(scores[r['wav']].max()>=threshold for r in local_val if r['class_id']==1)
   bg_fp=int(np.sum(pv[yv==0,2]>=threshold))
   critical={word:{'total':int(mask.sum()),'false':int(np.sum(pv[mask,2]>=threshold))} for word,mask in critical_masks.items()}
   trial['diagnostics'].append({'threshold':float(threshold),'sc_recall':sc['keyword_recall'],'sc_fp':sc['other_speech_false_activations']/max(1,sc['other_speech_total']),'mswc_recall':ms['keyword_recall'],'mswc_fp':ms['other_speech_false_activations']/max(1,ms['other_speech_total']),'libri_fp':long['other_speech_false_activations']/max(1,long['other_speech_total']),'background_fp':bg_fp,'local_negative_clips_triggered':int(local_fp),'local_stop_min_phase':int(min(counts)),'critical_words':critical})
   if bg_fp:continue
   if any(v['false']>int(v['total']*.05) for v in critical.values()):continue
   if sc['keyword_recall']<.8 or sc['other_speech_false_activations']/max(1,sc['other_speech_total'])>.005:continue
   if ms['keyword_total']==0 or ms['keyword_recall']<.7 or ms['other_speech_false_activations']/max(1,ms['other_speech_total'])>.01:continue
   if long['other_speech_false_activations']/max(1,long['other_speech_total'])>.005:continue
   if any(scores[r['wav']].max()>=threshold for r in local_val if r['class_id']==1):continue
   counts=[sum(scores[r['wav']][phase::10].max()>=threshold for r in local_val if r['class_id']==2) for phase in range(10)]
   if min(counts)<3:continue
   rank=(int(min(counts)),float((sc['keyword_recall']+ms['keyword_recall'])/2),-float(threshold))
   candidate={'checkpoint':checkpoint.name,'threshold':float(threshold),'rank':rank,'validation_by_source':b,'local_phase_stop_counts':[int(c) for c in counts]}
   trial['eligible'].append(candidate)
   if best is None or rank>tuple(best['rank']):best=candidate
  trials.append(trial);print('CHECKPOINT',checkpoint.name,'eligible',len(trial['eligible']),flush=True)
 dump(DEST/'validation_selection.json',trials)
 if best is None:
  dump(DEST/'status.json',{'status':'rejected on validation','test_evaluated':False,'next':'Inspect validation errors; do not promote failed checkpoint or tune on test data.'});print('REJECTED: expanded test remains unscored.',flush=True);return
 blob=(DEST/(Path(best['checkpoint']).stem+'.tflite')).read_bytes();(DEST/'stop_int8.tflite').write_bytes(blob);best['model_sha256']=hashlib.sha256(blob).hexdigest();dump(DEST/'frozen_selection.json',best);print('FROZEN',best['checkpoint'],best['threshold'],flush=True)
 rt=runtime(blob);threshold=best['threshold']
 xte=np.load(CACHE/'x_test.npy',mmap_mode='r');yte=np.load(CACHE/'y_test.npy');ter=json.loads((CACHE/'rows_test.json').read_text());pred=quantized_predictions(rt,xte)
 test=rows(local_manifest,'test');checks={r['wav']:scan_recording(rt,Path(r['path']),threshold) for r in test}
 result={'model_bytes':len(blob),'threshold':threshold,'model_sha256':best['model_sha256'],'expanded_test':breakdown(yte,pred,ter,threshold),'local_reused_test':{'summary':replay_summary(checks,test),'recordings':checks},'test_by_mswc_word':{word:metrics(yte[mask],pred[mask],threshold) for word in sorted({r['word'] for r in ter if r['source']=='mswc'}) if np.any(mask:=np.array([r['source']=='mswc' and r['word']==word for r in ter]))},'notes':['Expanded test partitions are within-corpus speaker-disjoint from training and validation.','Local recordings are one speaker and reused evaluation; not fresh independent evidence.','Automatically aligned MSWC clips may contain label/boundary errors.','Clip FP rate is not false activations per hour. Full-utterance negative replay is a separate report.']}
 dump(DEST/'metrics.json',result)
 # Baseline comparison uses the same evaluation inputs, without tuning either threshold.
 old=runtime((BASE/'stop_model_reviewed_v10/stop_int8.tflite').read_bytes());oldpred=quantized_predictions(old,xte)
 dump(DEST/'baseline_v10_comparison.json',{'threshold':.8671875,'expanded_test':breakdown(yte,oldpred,ter,.8671875)})
 (DEST/'stop_model_data.h').write_text('#pragma once\n#include <stdint.h>\n'+emit_array('g_stop_model',np.frombuffer(blob,np.uint8),'unsigned char')+f'const unsigned int g_stop_model_len = {len(blob)};\n')
 ids=[int(np.flatnonzero(yt==c)[j]) for c in range(3) for j in range(2)]
 for word in ['short','start','stark']:
  candidates=[i for i,r in enumerate(tr) if r['word']==word and r['source']=='mswc']
  if candidates:ids.append(candidates[0])
 inp=rt.get_input_details()[0];out=rt.get_output_details()[0];xx=xt[ids];pp=quantized_predictions(rt,xx)
 qi=np.clip(np.rint(xx/inp['quantization'][0])+inp['quantization'][1],-128,127).astype(np.int8);qo=np.rint(pp/out['quantization'][0]+out['quantization'][1]).astype(np.int8)
 (DEST/'test_vectors.h').write_text('#pragma once\n#include <stdint.h>\n// Expected outputs from BUILTIN_REF, not a desktop acceleration delegate.\n'+emit_array('g_test_inputs',qi,'int8_t')+emit_array('g_test_outputs',qo,'int8_t')+f'const unsigned int g_test_count = {len(ids)};\nconst unsigned int g_input_size = 1176;\n')
 dump(DEST/'status.json',{'status':'evaluated','physical_board_test':'pending','streaming_negative_test':'pending'});print('RESULT',json.dumps(result['expanded_test']),flush=True)
if __name__=='__main__':main()
