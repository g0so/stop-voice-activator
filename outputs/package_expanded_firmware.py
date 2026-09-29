#!/usr/bin/env python3
"""Package a frozen expanded model without modifying the working V10 firmware."""
import json,hashlib,shutil,re,argparse
from pathlib import Path
BASE=Path(__file__).resolve().parent

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--version',type=int,default=12);a=parser.parse_args();version=f'V{a.version}';folder=f'live_stop_expanded_v{a.version}'
 model=BASE/f'stop_model_expanded_v{a.version}';old=BASE/'live_stop_reviewed_v10';dest=BASE/folder
 selected=json.loads((model/'frozen_selection.json').read_text());metrics=json.loads((model/'metrics.json').read_text())
 assert selected['model_sha256']==hashlib.sha256((model/'stop_int8.tflite').read_bytes()).hexdigest()==metrics['model_sha256']
 assert 0<selected['threshold']<1
 dest.mkdir(exist_ok=True)
 for name in ['frontend.cpp','frontend.h','frontend_tables.h','window_centering.h']:shutil.copy2(old/name,dest/name)
 for name in ['stop_model_data.h','test_vectors.h']:shutil.copy2(model/name,dest/name)
 code=(old/'live_stop_reviewed_v10.ino').read_text()
 code=re.sub(r'constexpr float STOP_THRESHOLD = [0-9.]+f;',f"constexpr float STOP_THRESHOLD = {selected['threshold']}f;",code)
 code=code.replace('REVIEWED MODEL V10-R1: checking six reference inputs',f'EXPANDED MODEL {version}: checking reference inputs').replace('READY V10-R1',f'READY {version}')
 (dest/(folder+'.ino')).write_text(code)
 (dest/'MODEL_PROVENANCE.json').write_text(json.dumps({'model_sha256':selected['model_sha256'],'threshold':selected['threshold'],'source_model_directory':str(model),'frontend':'Unchanged V10 per-band temporal mean centering','reference_outputs':'TFLite BUILTIN_REF','physical_board_status':'Not uploaded or measured yet'},indent=2)+'\n')
 print(dest/(folder+'.ino'))
if __name__=='__main__':main()
