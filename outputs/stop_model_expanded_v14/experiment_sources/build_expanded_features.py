#!/usr/bin/env python3
"""Reproducible wave-to-feature cache for expanded public STOP training."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
import json,hashlib,wave
from pathlib import Path
from collections import Counter
import numpy as np
from audio_features import features as raw_features,augment,synthetic_background
BASE=Path(__file__).resolve().parent;ROOT=BASE/'dataset/expanded_public';CACHE=BASE.parent/'work/expanded_features_v11';SEED=20260929

def audio(path):
 with wave.open(str(path)) as w:
  assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
  return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768

def features(a):
 x=raw_features(a);return (x-x.mean(axis=0,keepdims=True)).astype(np.float32)

def one_second(a,start=0):return np.pad(a[start:start+16000],(0,max(0,16000-len(a[start:start+16000]))))

def main():
 CACHE.mkdir(parents=True,exist_ok=True);manifest=json.loads((ROOT/'manifest.json').read_text());local=json.loads((BASE/'reviewed_restart_manifest.json').read_text())
 assert {'speech_commands_v002','mswc','librispeech_dev_clean'} <= {r['source'] for r in manifest},'Wait for all three sources'
 noise_paths=sorted((ROOT/'speech_commands_v002/_background_noise_').glob('*.wav'));assert len(noise_paths)>=6
 noises=[audio(p) for p in noise_paths[:4]]
 fan=BASE/'fan_noise_new.wav'
 if fan.exists():noises.append(audio(fan))
 summary={}
 for split_i,split in enumerate(['train','validation','test']):
  rng=np.random.default_rng(SEED+split_i);tasks=[]
  for r in manifest:
   if r['split']!=split:continue
   if r['source']=='librispeech_dev_clean':
    with wave.open(r['path']) as w:n=w.getnframes()
    if n<16000:continue
    for start in np.unique(np.linspace(0,n-16000,min(8 if split=='train' else 4,max(1,n//16000)),dtype=int)):
     tasks.append({**r,'offset':int(start),'variant':'clean'})
   else:
    tasks.append({**r,'offset':0,'variant':'clean'})
    if split=='train':
     if r['label']==2:tasks.extend([{**r,'offset':0,'variant':'positive_aug'} for _ in range(2)])
     elif r['source']=='mswc':tasks.append({**r,'offset':0,'variant':'negative_aug'})
  # Reviewed local data remains a small supplement. Evaluation clips are complete-word automatic crops here;
  # complete five-second replay is handled separately in training/evaluation.
  for r in local['recordings'][split]:
   from scipy.signal import butter,sosfiltfilt
   path=BASE.parent/r['wav'];a=audio(path)
   band=sosfiltfilt(butter(4,[300,3500],btype='bandpass',fs=16000,output='sos'),a)
   e=np.convolve(band*band,np.ones(3200)/3200,mode='same');peak=8000+int(np.argmax(e[8000:56000]));start=int(np.clip(peak-8000,0,len(a)-16000))
   for i in range(20 if split=='train' else 1):tasks.append({'path':str(path),'source':'reviewed_device','word':r['word'],'speaker':'device:s01','split':split,'label':2 if r['word']=='stop' else 1,'offset':start,'variant':'local_aug' if split=='train' and i else 'clean'})
  for i in range(6000 if split=='train' else 500):tasks.append({'path':'','source':'background','word':'background','speaker':'noise','split':split,'label':0,'offset':0,'variant':'noise','noise_index':i})
  x=np.lib.format.open_memmap(CACHE/f'x_{split}.npy',mode='w+',dtype=np.float32,shape=(len(tasks),49,24,1));y=np.asarray([r['label'] for r in tasks],np.int32)
  cached_path=None;cached_audio=None
  heldout_noise=audio(noise_paths[4 if split=='validation' else 5]) if split!='train' else None
  for i,r in enumerate(tasks):
   if r['variant']=='noise':
    if r['noise_index']%2==0:a=synthetic_background(rng)
    else:
     n=noises[int(rng.integers(len(noises)))] if split=='train' else heldout_noise
     a=one_second(n,int(rng.integers(max(1,len(n)-16000+1)))).copy();a*=10**rng.uniform(-.8,.3)
   else:
    if cached_path!=r['path']:cached_path=r['path'];cached_audio=audio(cached_path)
    a=one_second(cached_audio,r['offset']).copy()
    if r['variant'] in {'positive_aug','local_aug'}:a=augment(a,rng)
    elif r['variant']=='negative_aug':
     shift=int(rng.integers(-6400,6401));a=np.roll(a,shift)
     if shift>0:a[:shift]=0
     elif shift<0:a[shift:]=0
     a*=10**rng.uniform(-.4,.3)
    if r['variant']!='clean' and split=='train' and rng.random()<.7:
     n=noises[int(rng.integers(len(noises)))];n=one_second(n,int(rng.integers(max(1,len(n)-16000+1)))).copy()
     n*=max(float(np.sqrt(np.mean(a*a))),.001)/(10**(rng.uniform(6,25)/20)*max(float(np.sqrt(np.mean(n*n))),1e-6));a+=n
   x[i]=features(np.clip(a,-1,1))
   if (i+1)%5000==0:print(split,i+1,'/',len(tasks),flush=True)
  x.flush();np.save(CACHE/f'y_{split}.npy',y)
  (CACHE/f'rows_{split}.json').write_text(json.dumps(tasks)+'\n')
  summary[split]={'examples':len(tasks),'sources':dict(Counter(r['source'] for r in tasks)),'class_counts':np.bincount(y,minlength=3).tolist()}
  print(split,summary[split],flush=True)
 summary['notes']=['Public corpus speaker splits fixed before augmentation.','Reviewed device evaluation is same-speaker, separate recordings; public evaluation is within-corpus speaker-disjoint.','Source background files partitioned: four train, one validation, one test; fan recording train-only.','Feature extraction is deterministic and does not score/select a model on test examples.']
 (CACHE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__':main()
