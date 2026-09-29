#!/usr/bin/env python3
"""Resume only the selected public datasets, verifying publisher hashes before use."""
import fcntl,hashlib,json,subprocess,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
BASE=Path(__file__).resolve().parent;WORK=BASE.parent/'work';DOWNLOAD=WORK/'downloads'
def digest(path,algorithm):
 h=hashlib.new(algorithm)
 with path.open('rb') as f:
  while chunk:=f.read(1024*1024):h.update(chunk)
 return h.hexdigest()
def fetch(r):
 p=DOWNLOAD/r['file'];log=WORK/('fetch_'+r['name']+'.log')
 if p.exists() and ('size' not in r or p.stat().st_size==r['size']) and digest(p,r['algorithm'])==r['checksum']:
  print('Already verified:',r['name'],flush=True);return
 if r['name']=='speech_commands_v002':
  with log.open('a') as out:subprocess.run([sys.executable,str(BASE/'download_public_archive.py'),r['url'],str(p),'--size',str(r['size']),'--md5',r['checksum']],stdout=out,stderr=subprocess.STDOUT,check=True)
 else:
  for attempt in range(1,11):
   print('Downloading',r['name'],'attempt',attempt,flush=True)
   with log.open('a') as out:
    code=subprocess.run(['curl','-sS','-L','--fail','--connect-timeout','30','--max-time','600','--speed-limit','1024','--speed-time','60','--continue-at','-','-o',str(p),r['url']],stdout=out,stderr=subprocess.STDOUT).returncode
   if code==0:break
   time.sleep(3)
  else:raise RuntimeError(f'{r["name"]}: transfer interrupted repeatedly; partial file retained')
 assert digest(p,r['algorithm'])==r['checksum'],f'Checksum mismatch: {p}; retained for inspection, not used'
 (DOWNLOAD/(r['file']+'.verified.json')).write_text(json.dumps(r,indent=2)+'\n')
 print('VERIFIED:',r['name'],flush=True)
def main():
 DOWNLOAD.mkdir(parents=True,exist_ok=True)
 with (WORK/'expanded_download.lock').open('w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit('The expanded-data downloader is already running.')
  rows=json.loads((BASE/'expanded_sources.json').read_text())
  errors=[]
  with ThreadPoolExecutor(max_workers=3) as pool:
   for future in as_completed([pool.submit(fetch,r) for r in rows]):
    try:future.result()
    except Exception as e:errors.append(str(e));print('ERROR:',e,flush=True)
  if errors:raise SystemExit('\n'.join(errors))
 print('ALL EXPANDED SOURCES VERIFIED',flush=True)
if __name__=='__main__':main()
