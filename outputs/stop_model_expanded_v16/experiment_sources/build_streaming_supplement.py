#!/usr/bin/env python3
"""Training-only rolling views of already-reviewed device recordings."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import json
from pathlib import Path
import numpy as np
from build_expanded_features import audio,features
from audio_features import augment
BASE=Path(__file__).resolve().parent;DEST=BASE.parent/'work/streaming_supplement'
DEST.mkdir(exist_ok=True);rng=np.random.default_rng(2026092914)
m=json.loads((BASE/'reviewed_restart_manifest.json').read_text());cache=BASE.parent/'work/expanded_features_v11'
rr=json.loads((cache/'rows_train.json').read_text());centers={r['path']:r['offset'] for r in rr if r['source']=='reviewed_device'}
xs=[];ys=[];rows=[]
for r in m['recordings']['train']:
 path=(BASE.parent/r['wav']).resolve();a=audio(path);positive=r['word']=='stop';center=centers[str(path)]
 starts=[center]*80 if positive else list(range(0,len(a)-15999,1280))*2
 for j,start in enumerate(starts):
  b=a[start:start+16000].copy()
  if positive:b=augment(b,rng)
  elif j>=len(starts)//2:
   b*=10**rng.uniform(-.3,.3)
   b+=rng.normal(0,rng.uniform(.0001,.001),len(b))
  xs.append(features(np.clip(b,-1,1)));ys.append(2 if positive else 1)
  rows.append({'path':str(path),'source':'reviewed_device','word':r['word'],'speaker':'device:s01','split':'train','label':ys[-1],'offset':start,'variant':'complete_recording_rolling_negative' if not positive else 'complete_word_positive_aug'})
np.save(DEST/'x.npy',np.asarray(xs,np.float32));np.save(DEST/'y.npy',np.asarray(ys,np.int32));(DEST/'rows.json').write_text(json.dumps(rows)+'\n');print({'examples':len(xs),'class_counts':np.bincount(ys,minlength=3).tolist(),'test_or_validation_recordings_used':False})
