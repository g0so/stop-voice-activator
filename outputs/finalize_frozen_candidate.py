#!/usr/bin/env python3
"""Post-freeze steps of train_expanded_keyword.py for a selection frozen outside the automatic gates."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from train_keyword import quantized_predictions,metrics,emit_array
from train_reviewed_wider import runtime,scan_recording,rows
from train_hard_negatives import replay_summary
from train_expanded_keyword import breakdown,dump
BASE=Path(__file__).resolve().parent;CACHE=BASE.parent/'work/expanded_features_v11'

def main():
 p=argparse.ArgumentParser();p.add_argument('--model-dir',required=True);a=p.parse_args();DEST=BASE/a.model_dir
 best=json.loads((DEST/'frozen_selection.json').read_text());blob=(DEST/'stop_int8.tflite').read_bytes()
 assert hashlib.sha256(blob).hexdigest()==best['model_sha256'] and not (DEST/'metrics.json').exists(),'Selection must be frozen; test is scored once'
 rt=runtime(blob);threshold=best['threshold']
 xte=np.load(CACHE/'x_test.npy',mmap_mode='r');yte=np.load(CACHE/'y_test.npy');ter=json.loads((CACHE/'rows_test.json').read_text());pred=quantized_predictions(rt,xte)
 local_manifest=json.loads((BASE/'reviewed_restart_manifest.json').read_text());test=rows(local_manifest,'test');checks={r['wav']:scan_recording(rt,Path(r['path']),threshold) for r in test}
 result={'model_bytes':len(blob),'threshold':threshold,'model_sha256':best['model_sha256'],'selection_basis':best.get('selection_basis'),'expanded_test':breakdown(yte,pred,ter,threshold),'local_reused_test':{'summary':replay_summary(checks,test),'recordings':checks},'test_by_mswc_word':{word:metrics(yte[mask],pred[mask],threshold) for word in sorted({r['word'] for r in ter if r['source']=='mswc'}) if np.any(mask:=np.array([r['source']=='mswc' and r['word']==word for r in ter]))},'notes':['Expanded test partitions are within-corpus speaker-disjoint from training and validation.','Local recordings are one speaker and reused evaluation; not fresh independent evidence.','Automatically aligned MSWC clips may contain label/boundary errors.','Clip FP rate is not false activations per hour. Full-utterance negative replay is a separate report.']}
 dump(DEST/'metrics.json',result)
 old=runtime((BASE/'stop_model_reviewed_v10/stop_int8.tflite').read_bytes());oldpred=quantized_predictions(old,xte)
 dump(DEST/'baseline_v10_comparison.json',{'threshold':.8671875,'expanded_test':breakdown(yte,oldpred,ter,.8671875),'test_by_mswc_word':{word:metrics(yte[mask],oldpred[mask],.8671875) for word in sorted({r['word'] for r in ter if r['source']=='mswc'}) if np.any(mask:=np.array([r['source']=='mswc' and r['word']==word for r in ter]))}})
 (DEST/'stop_model_data.h').write_text('#pragma once\n#include <stdint.h>\n'+emit_array('g_stop_model',np.frombuffer(blob,np.uint8),'unsigned char')+f'const unsigned int g_stop_model_len = {len(blob)};\n')
 # Same reference inputs as the trainer: two per class plus one SHORT/START/STARK MSWC training example.
 xt=np.load(CACHE/'x_train.npy',mmap_mode='r');yt=np.load(CACHE/'y_train.npy');tr=json.loads((CACHE/'rows_train.json').read_text())
 ids=[int(np.flatnonzero(yt==c)[j]) for c in range(3) for j in range(2)]
 for word in ['short','start','stark']:
  candidates=[i for i,r in enumerate(tr) if r['word']==word and r['source']=='mswc']
  if candidates:ids.append(candidates[0])
 inp=rt.get_input_details()[0];out=rt.get_output_details()[0];xx=xt[ids];pp=quantized_predictions(rt,xx)
 qi=np.clip(np.rint(xx/inp['quantization'][0])+inp['quantization'][1],-128,127).astype(np.int8);qo=np.rint(pp/out['quantization'][0]+out['quantization'][1]).astype(np.int8)
 (DEST/'test_vectors.h').write_text('#pragma once\n#include <stdint.h>\n// Expected outputs from BUILTIN_REF, not a desktop acceleration delegate.\n'+emit_array('g_test_inputs',qi,'int8_t')+emit_array('g_test_outputs',qo,'int8_t')+f'const unsigned int g_test_count = {len(ids)};\nconst unsigned int g_input_size = 1176;\n')
 dump(DEST/'status.json',{'status':'evaluated baseline-improvement candidate (fails original V11 gates)','physical_board_test':'pending','streaming_negative_test':'pending'})
 print('RESULT',json.dumps({k:{m:v[m] for m in ['keyword_recall','other_speech_false_activations','other_speech_total']} for k,v in result['expanded_test'].items()}),flush=True)
 print('LOCAL',json.dumps(result['local_reused_test']['summary']['phase_results'][0]),flush=True)
if __name__=='__main__':main()
