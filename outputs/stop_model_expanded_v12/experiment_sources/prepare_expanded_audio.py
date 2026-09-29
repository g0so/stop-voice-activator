#!/usr/bin/env python3
"""Prepare licensed public speech with speaker-separated manifests; preserve old datasets."""
import argparse,csv,hashlib,io,json,re,shutil,subprocess,tarfile,wave
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
BASE=Path(__file__).resolve().parent;ROOT=BASE/'dataset/expanded_public';DOWNLOAD=BASE.parent/'work/downloads'
TARGET_WORDS={'stop','start','short','stark','stot','shop','stock','stopped','stopping','starts','started','shot','spot','step','steps','star','stars','store','storm','story','strong','street','stand','stay','still','shut','shit','top'}

def split_for(speaker,prefix='voice-v1:'):
 n=int(hashlib.sha256((prefix+speaker).encode()).hexdigest()[:8],16)%100
 return 'train' if n<80 else ('validation' if n<90 else 'test')

def copy_member(t,m,dst):
 if dst.exists():
  assert dst.stat().st_size==m.size,(dst,m.size);return
 dst.parent.mkdir(parents=True,exist_ok=True)
 tmp=dst.with_suffix(dst.suffix+'.partial')
 with t.extractfile(m) as src,tmp.open('wb') as out:shutil.copyfileobj(src,out)
 assert tmp.stat().st_size==m.size;tmp.replace(dst)

def prepare_sc():
 archive=DOWNLOAD/'speech_commands_v0.02.tar.gz'
 h=hashlib.md5()
 with archive.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 assert h.hexdigest()=='6b74f3901214cb2c2934e98196829835','Incomplete or corrupted Speech Commands archive'
 root=ROOT/'speech_commands_v002';root.mkdir(parents=True,exist_ok=True)
 with tarfile.open(archive,'r|gz') as t:
  for m in t:
   if not m.isfile():continue
   parts=Path(m.name).parts
   if '..' in parts or Path(m.name).is_absolute():raise ValueError(m.name)
   if len(parts)==2 and (m.name.endswith('.wav') or parts[0]=='_background_noise_'):copy_member(t,m,root.joinpath(*parts))
   elif len(parts)==1 and parts[0] in {'README.md','LICENSE','validation_list.txt','testing_list.txt'}:copy_member(t,m,root/parts[0])
 rows=[]
 for p in sorted(root.glob('*/*.wav')):
  if p.parent.name=='_background_noise_':continue
  speaker=p.stem.split('_nohash_')[0]
  with wave.open(str(p)) as w:
   assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
   assert 0<w.getnframes()<=16000
  rows.append({'path':str(p),'source':'speech_commands_v002','word':p.parent.name,'speaker':'sc:'+speaker,'split':split_for(speaker),'label':2 if p.parent.name=='stop' else 1})
 assert len(rows)==105829,len(rows)
 return rows

def prepare_mswc():
 meta=DOWNLOAD/'mswc_en_hf_splits.tar.gz';lookup={}
 with tarfile.open(meta,'r|gz') as t:
  for m in t:
   if not m.isfile() or not m.name.endswith('.csv'):continue
   f=(line.decode('utf8') for line in t.extractfile(m))
   reader=csv.DictReader(f)
   for r in reader:
    r={k.upper():v for k,v in r.items()}
    word=r['WORD'].lower()
    if word not in TARGET_WORDS or r['VALID'].lower() not in {'true','1'}:continue
    if not r.get('SPEAKER') or r['SPEAKER'] in {'NA','NAN'}:continue
    key=r['LINK'].replace('/','_')
    lookup[key]={'word':word,'speaker':'mswc:'+r['SPEAKER'],'split':split_for(r['SPEAKER'],'voice-v1:mswc:')}
 rows=[];seen=set();root=ROOT/'mswc'
 for archive in sorted(DOWNLOAD.glob('mswc_en_train_*.tar.gz')):
  with tarfile.open(archive,'r|gz') as t:
   for m in t:
    if not m.isfile():continue
    key=Path(m.name).name
    if key not in lookup or key in seen:continue
    r=lookup[key];seen.add(key)
    # Preserve compressed source and create fixed-format WAV for training.
    opus=root/'opus'/key;copy_member(t,m,opus)
    wav=root/'wav'/Path(key).with_suffix('.wav');wav.parent.mkdir(parents=True,exist_ok=True)
    rows.append({'path':str(wav),'source':'mswc','word':r['word'],'speaker':r['speaker'],'split':r['split'],'label':2 if r['word']=='stop' else 1})
 def decode(r):
  wav=Path(r['path']);opus=root/'opus'/wav.with_suffix('.opus').name
  if not wav.exists():
   tmp=wav.with_suffix('.partial.wav')
   subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-threads','1','-i',str(opus),'-ac','1','-ar','16000','-c:a','pcm_s16le','-threads','1',str(tmp)],check=True)
   tmp.replace(wav)
 with ThreadPoolExecutor(max_workers=4) as pool:
  for i,_ in enumerate(pool.map(decode,rows),1):
   if i%1000==0:print('MSWC decoded',i,'/',len(rows),flush=True)
 print('MSWC selected words',dict(Counter(r['word'] for r in rows)),flush=True)
 return rows

def prepare_libri():
 root=ROOT/'librispeech';root.mkdir(parents=True,exist_ok=True)
 with tarfile.open(DOWNLOAD/'librispeech_dev_clean.tar.gz','r|gz') as t:
  for m in t:
   if not m.isfile():continue
   p=Path(m.name)
   if p.is_absolute() or '..' in p.parts:raise ValueError(m.name)
   if p.suffix in {'.txt','.flac'} or p.name in {'LICENSE.TXT','README.TXT','SPEAKERS.TXT'}:copy_member(t,m,root/p)
 rows=[]
 for p in sorted(root.rglob('*.trans.txt')):
  for line in p.read_text().splitlines():
   key,text=line.split(' ',1)
   # Exclude explicit keyword and inflected forms to avoid mislabeled positives.
   if re.search(r'\bSTOP\w*',text):continue
   audio=p.parent/(key+'.flac');speaker=key.split('-')[0]
   wav=audio.with_suffix('.wav')
   if not wav.exists():
    tmp=wav.with_suffix('.partial.wav');subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(audio),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(tmp)],check=True);tmp.replace(wav)
   words=sorted(TARGET_WORDS.intersection(text.lower().split()))
   rows.append({'path':str(wav),'source':'librispeech_dev_clean','word':'continuous_negative','speaker':'libri:'+speaker,'split':split_for(speaker,'voice-v1:libri:'),'label':1,'transcript':text,'confusables':words})
 return rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',choices=['sc','mswc','libri','all'],default='all');a=p.parse_args();ROOT.mkdir(parents=True,exist_ok=True)
 parts=[]
 for source,fn in [('sc',prepare_sc),('mswc',prepare_mswc),('libri',prepare_libri)]:
  out=ROOT/(source+'_manifest.json')
  if a.source in {source,'all'}:
   rr=fn();out.write_text(json.dumps(rr,indent=2)+'\n');print(source,len(rr),dict(Counter(r['split'] for r in rr)),flush=True)
  if out.exists():parts+=json.loads(out.read_text())
 speakers=defaultdict(set)
 for r in parts:speakers[r['split']].add(r['speaker'])
 assert not(speakers['train']&speakers['validation'] or speakers['train']&speakers['test'] or speakers['validation']&speakers['test'])
 (ROOT/'manifest.json').write_text(json.dumps(parts,indent=2)+'\n')
 summary={'total':len(parts),'by_source':dict(Counter(r['source'] for r in parts)),'by_split':dict(Counter(r['split'] for r in parts)),'speakers_by_split':{k:len(v) for k,v in speakers.items()},'word_counts':dict(Counter(r['word'] for r in parts)),'speaker_overlap':0,'notes':['Speaker IDs kept disjoint within each corpus; identities across unrelated corpora are not linked.','MSWC is automatically aligned and may contain extraction/label errors; VALID=True clips only.','LibriSpeech dev-clean is repurposed with a documented custom speaker split; results are not the official LibriSpeech benchmark.','Speech Commands uses the existing project speaker-hash split, not upstream validation/test lists.']}
 (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary,flush=True)
if __name__=='__main__':main()
