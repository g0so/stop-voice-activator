"""Static repository check; no model execution, compilation, training or network."""
from pathlib import Path
import ast,hashlib,json,re,subprocess,wave
root=Path(__file__).resolve().parents[1]
for p in root.rglob('*.py'):
 if not any(x in p.parts for x in ['.venv','work']):ast.parse(p.read_text(),filename=str(p))
m=json.loads((root/'outputs/reviewed_restart_manifest.json').read_text())
for split,count in [('train',16),('validation',8),('test',8)]:
 assert len(m['recordings'][split])==count
 for r in m['recordings'][split]:
  assert (root/r['metadata']).is_file()
  with wave.open(str(root/r['wav'])) as w:assert (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getnframes())==(1,2,16000,80000)
folder=root/'outputs/live_stop_reviewed_v10'
for name in ['live_stop_reviewed_v10.ino','frontend.cpp','frontend.h','frontend_tables.h','window_centering.h','stop_model_data.h','test_vectors.h']:assert (folder/name).is_file(),name
blob=(root/'outputs/stop_model_reviewed_v10/stop_int8.tflite').read_bytes()
assert hashlib.sha256(blob).hexdigest()=='f4cfb4a730d8318e5239c1cb5c3a234ef904744c5233fbc28d183379fc0d97e0'
s=(folder/'stop_model_data.h').read_text();body=s.split('{',1)[1].split('}',1)[0]
assert bytes(map(int,re.findall(r'\d+',body)))==blob
public_cache=root/'outputs/dataset/expanded_public'
if public_cache.exists():
 result=subprocess.run(
  ['git','check-ignore','--quiet',str(public_cache.relative_to(root))],
  cwd=root,check=False,
 )
 assert result.returncode==0,'Public audio cache exists and is not excluded from Git'
print('PASS: Python syntax, 32 reviewed recordings, complete firmware sources, baseline model/header hash, public cache excluded. No builds or inference performed.')
