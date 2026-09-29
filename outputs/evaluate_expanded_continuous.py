#!/usr/bin/env python3
"""Replay complete held-out non-keyword utterances at ten 200 ms timing phases."""
import json,hashlib,wave,argparse
from pathlib import Path
import numpy as np
from train_reviewed_wider import runtime,scan_recording
BASE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--model-dir',default='stop_model_expanded_v12');p.add_argument('--split',choices=['validation','test'],default='test');a=p.parse_args()
 dest=BASE/a.model_dir
 assert (dest/'frozen_selection.json').exists(),'Freeze model and threshold before test replay'
 selection=json.loads((dest/'frozen_selection.json').read_text())
 manifest=json.loads((BASE/'dataset/expanded_public/manifest.json').read_text())
 rows=[r for r in manifest if r['source']=='librispeech_dev_clean' and r['split']==a.split]
 runtimes={'expanded':(runtime((dest/'stop_int8.tflite').read_bytes()),selection['threshold']), 'v10':(runtime((BASE/'stop_model_reviewed_v10/stop_int8.tflite').read_bytes()),.8671875)}
 hashes={'expanded':selection['model_sha256'],'v10':hashlib.sha256((BASE/'stop_model_reviewed_v10/stop_int8.tflite').read_bytes()).hexdigest()}
 cache=dest/('continuous_'+a.split);cache.mkdir(exist_ok=True)
 totals={k:{'activations_by_phase':[0]*10,'scored_seconds_by_phase':[0.]*10,'utterances_triggered_by_phase':[0]*10,'confusable_utterances':0,'confusable_triggered_by_phase':[0]*10} for k in runtimes}
 for i,r in enumerate(rows):
  path=Path(r['path'])
  with wave.open(str(path)) as w:duration=w.getnframes()/w.getframerate()
  for name,(rt,threshold) in runtimes.items():
   saved=cache/(name+'_'+path.stem+'.json')
   if saved.exists():
    scan=json.loads(saved.read_text());assert scan['model_sha256']==hashes[name] and scan['threshold']==threshold
   else:
    scan=scan_recording(rt,path,threshold);scan.update({'model_sha256':hashes[name],'audio':str(path),'duration':duration,'transcript':r['transcript'],'confusables':r['confusables']});saved.write_text(json.dumps(scan)+'\n')
   t=totals[name]
   if r['confusables']:t['confusable_utterances']+=1
   for j,phase in enumerate(scan['phase_results']):
    n=len(phase['activation_times']);t['activations_by_phase'][j]+=n;t['utterances_triggered_by_phase'][j]+=int(n>0)
    # Each utterance restarts. Exclude initial window filling time from exposure.
    t['scored_seconds_by_phase'][j]+=max(0,duration-(.99+j*.02))
    if r['confusables']:t['confusable_triggered_by_phase'][j]+=int(n>0)
  if (i+1)%25==0:print('Continuous replay',i+1,'/',len(rows),flush=True)
 for t in totals.values():
  t['false_activations_per_hour_by_phase']=[round(n/(s/3600),3) if s else None for n,s in zip(t['activations_by_phase'],t['scored_seconds_by_phase'])]
  t['worst_phase_false_activations_per_hour']=max(t['false_activations_per_hour_by_phase'])
 result={'utterances':len(rows),'split':a.split,'models':totals,'notes':['Held-out LibriSpeech sentences without STOP/inflections in supplied transcripts; not live-room audio.','Every utterance restarts state. Ten phases replay the same speech; they are not ten independent hours of evidence.','Trigger logic mirrors current firmware: threshold crossing, rearm after two scores below .3 and at least one second since trigger.','The initial .99 seconds plus phase offset of each utterance is excluded from scored exposure.','Thresholds frozen before replay; no tuning on these results.']}
 (dest/('continuous_'+a.split+'_summary.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
