#!/usr/bin/env python3
"""Explicit-window Redis capacity observation; no background daemon or cloud change."""
import argparse,json,time
from data import private_json,validate_connection
from resp import Redis

def sample(r,baseline_oom=None):
 info=r.info();used=int(info['used_memory']);limit=int(info['maxmemory']);raw=info.get('errorstat_OOM','count=0');oom=int(raw.split('count=')[-1].split(',')[0]);ratio=used/limit if limit else 1
 level='critical'if ratio>=.8 or baseline_oom is not None and oom>baseline_oom else'warning'if ratio>=.7 else'normal'
 return {'used_memory':used,'maxmemory':limit,'ratio':round(ratio,4),'headroom_bytes':limit-used,'policy':info.get('maxmemory_policy'),'oom_count':oom,'evicted_keys':int(info.get('evicted_keys',0)),'connected_clients':int(info.get('connected_clients',0)),'level':level}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--connection',required=True);p.add_argument('--seconds',type=int,default=0);p.add_argument('--interval',type=int,default=30);a=p.parse_args()
 if a.seconds<0 or a.interval<1:raise ValueError('Invalid observation window')
 cfg=validate_connection(private_json(a.connection));r=Redis(cfg)
 try:
  first=sample(r);start=time.monotonic();baseline=first['oom_count'];failed=False
  while True:
   row=sample(r,baseline);row['elapsed_seconds']=round(time.monotonic()-start);print(json.dumps(row),flush=True);failed|=row['level']=='critical'
   remaining=a.seconds-(time.monotonic()-start)
   if remaining<=0:break
   time.sleep(min(a.interval,remaining))
  if failed:raise SystemExit(2)
 finally:r.close()
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'monitor':'failed','error_type':type(e).__name__}));raise SystemExit(1)from None
