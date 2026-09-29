#!/usr/bin/env python3
"""Resumable four-connection downloader for a public archive, with exact ranges and checksum."""
import argparse,hashlib,json,re,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('output',type=Path);p.add_argument('--size',type=int,required=True);p.add_argument('--md5',required=True);a=p.parse_args()
 folder=a.output.with_suffix(a.output.suffix+'.parts');folder.mkdir(exist_ok=True);planpath=folder/'plan.json'
 if planpath.exists():
  plan=json.loads(planpath.read_text());assert plan['url']==a.url and plan['size']==a.size
 else:
  prefix=0
  if a.output.exists():
   prefix=a.output.stat().st_size
   if prefix==a.size:
    assert hashlib.md5(a.output.read_bytes()).hexdigest()==a.md5;print('Already verified');return
   a.output.rename(folder/'prefix')
  plan={'url':a.url,'size':a.size,'md5':a.md5,'prefix':prefix};planpath.write_text(json.dumps(plan,indent=2))
 jobs=[(i,start,min(start+16*1024*1024,a.size)-1) for i,start in enumerate(range(plan['prefix'],a.size,16*1024*1024))]
 def fetch(job):
  i,start,end=job;out=folder/f'{i:04d}';head=folder/f'{i:04d}.headers';size=end-start+1
  if out.exists() and out.stat().st_size==size and (folder/f'{i:04d}.ok').exists():return size
  part=folder/f'{i:04d}.partial'
  subprocess.run(['curl','-sS','-L','--fail','--retry','4','--retry-all-errors','--speed-limit','1024','--speed-time','60','--connect-timeout','30','--max-time','600','--max-filesize',str(size),'-r',f'{start}-{end}','-D',str(head),'-o',str(part),a.url],check=True)
  assert part.stat().st_size==size
  assert f'content-range: bytes {start}-{end}/{a.size}' in head.read_text().lower()
  part.replace(out);(folder/f'{i:04d}.ok').touch();return size
 done=plan['prefix'];started=time.monotonic()
 with ThreadPoolExecutor(max_workers=4) as pool:
  for f in as_completed([pool.submit(fetch,j) for j in jobs]):
   done+=f.result();print(f'{done/a.size:.1%} complete; {(done-plan["prefix"])/max(1,time.monotonic()-started)/1e6:.2f} MB/s',flush=True)
 tmp=a.output.with_suffix(a.output.suffix+'.assembling');digest=hashlib.md5()
 with tmp.open('wb') as dst:
  sources=([folder/'prefix'] if plan['prefix'] else [])+[folder/f'{i:04d}' for i,_,_ in jobs]
  for source in sources:
   with source.open('rb') as src:
    while chunk:=src.read(1024*1024):digest.update(chunk);dst.write(chunk)
 assert tmp.stat().st_size==a.size and digest.hexdigest()==a.md5,(tmp.stat().st_size,digest.hexdigest())
 tmp.replace(a.output);print('VERIFIED',a.output,flush=True)
if __name__=='__main__':main()
