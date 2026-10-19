#!/usr/bin/env python3
"""Private binary-safe Redis snapshot preparation; restore is explicit and fenced.

Credentials and snapshot keys/values must never be printed or committed.
Expired keys are never resurrected; target databases must be empty.
"""
import argparse,base64,hashlib,json,os,time
from pathlib import Path
from resp import Redis,RedisError,old_config
DBS=list(range(9));MAX_DUMP_BYTES=64*1024*1024

def private_json(path):
 p=Path(path)
 if p.is_symlink() or p.stat().st_mode & 0o077:raise ValueError('Private input permissions required')
 return json.loads(p.read_text())

def save_private(path,value):
 p=Path(path)
 if p.parent.is_symlink() or p.parent.stat().st_mode & 0o077:raise ValueError('Private destination directory required')
 with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w')as f:
  json.dump(value,f);f.flush();os.fsync(f.fileno())

def frozen_receipt(path,source_host):
 r=private_json(path);now=int(time.time()*1000)
 if not r.get('operator_attested_all_writers_fenced') or r.get('source_host')!=source_host:raise ValueError('Reviewed global writer fence required')
 if not 0<r['expires_ms']-now<=600000:raise ValueError('Writer fence expired or validity exceeds ten minutes')
 expected={'servera':{'qs-apiserver','iam-apiserver','qs-collection-server-1','qs-collection-server-2'},'serverd':{'qs-worker-runtime-1','qs-worker-runtime-2','qs-worker-runtime-3'}}
 if set(r['nodes'])!=set(expected):raise ValueError('Incomplete host fence')
 for host,names in expected.items():
  rows=r['nodes'][host]
  if {x['name']for x in rows}!=names or any(x['running']or x['restart_policy']!='no'for x in rows):raise ValueError('Writers are not stopped with restart disabled')
 return r

def digest(entries):return hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def export_snapshot(client,consistent=False):
 entries=[];total=0
 for db in DBS:
  for key in client.scan(db):
   client.cmd('MULTI');client.cmd('DUMP',key);client.cmd('PEXPIRETIME',key);client.cmd('TYPE',key)
   blob,deadline,typ=client.cmd('EXEC')
   if blob is None or deadline==-2 or typ==b'none':continue
   if deadline!=-1 and deadline<=client.now_ms():continue
   total+=len(blob)
   if total>MAX_DUMP_BYTES:raise ValueError('Snapshot exceeds reviewed size bound')
   entries.append({'db':db,'key_b64':base64.b64encode(key).decode(),'dump_b64':base64.b64encode(blob).decode(),'type':typ.decode(),'expires_ms':deadline,'dump_sha256':hashlib.sha256(blob).hexdigest()})
 return {'format':1,'created_ms':client.now_ms(),'consistent':consistent,'entries':entries,'dump_bytes':total,'sha256':digest(entries)}

def validate_snapshot(s):
 if s['format']!=1 or digest(s['entries'])!=s['sha256']:raise ValueError('Snapshot checksum mismatch')
 seen=set();total=0
 for x in s['entries']:
  key=base64.b64decode(x['key_b64'],validate=True);blob=base64.b64decode(x['dump_b64'],validate=True);identity=(x['db'],key);total+=len(blob)
  if identity in seen or x['db']not in DBS or not key or x['expires_ms']<-1:raise ValueError('Invalid snapshot key metadata')
  if hashlib.sha256(blob).hexdigest()!=x['dump_sha256']:raise ValueError('Dump checksum mismatch')
  seen.add(identity)
 if total>MAX_DUMP_BYTES or total!=s['dump_bytes']:raise ValueError('Dump size mismatch')
 return s

def restore_snapshot(client,s,apply=False):
 validate_snapshot(s)
 for db in DBS:
  client.cmd('SELECT',db)
  if client.cmd('DBSIZE')!=0:raise ValueError('Target DB is nonempty; no overwrite allowed')
 live=[x for x in s['entries']if x['expires_ms']==-1 or x['expires_ms']>client.now_ms()]
 out={'dry_run':not apply,'eligible':len(live),'expired_skipped':len(s['entries'])-len(live),'restored':0}
 if not apply:return out
 if not s['consistent']:raise ValueError('Cannot restore a live, unfenced backup')
 # No REPLACE and no FLUSH: an unexpected key always aborts rather than overwrites.
 for x in live:
  if x['expires_ms']!=-1 and x['expires_ms']<=client.now_ms():out['expired_skipped']+=1;continue
  client.cmd('SELECT',x['db']);key=base64.b64decode(x['key_b64']);blob=base64.b64decode(x['dump_b64'])
  args=['RESTORE',key,0 if x['expires_ms']==-1 else x['expires_ms'],blob]
  if x['expires_ms']!=-1:args.append('ABSTTL')
  client.cmd(*args);out['restored']+=1
 return out

def verify_snapshot(client,s):
 validate_snapshot(s);mismatch=0;missing=0;verified=0;expired=0;seen=set()
 for x in s['entries']:
  if x['expires_ms']!=-1 and x['expires_ms']<=client.now_ms():expired+=1;continue
  key=base64.b64decode(x['key_b64']);client.cmd('SELECT',x['db'])
  blob=client.cmd('DUMP',key);deadline=client.cmd('PEXPIRETIME',key)
  if blob is None:
   if x['expires_ms']!=-1 and x['expires_ms']<=client.now_ms():expired+=1;continue
   missing+=1;continue
  if hashlib.sha256(blob).hexdigest()!=x['dump_sha256']or deadline!=x['expires_ms']:mismatch+=1
  else:verified+=1
  seen.add((x['db'],key))
 extra=sum((db,k)not in seen for db in DBS for k in client.scan(db)if client.cmd('PEXPIRETIME',k)!=-2)
 return {'verified':verified,'expired':expired,'missing':missing,'mismatch':mismatch,'extra':extra,'pass':not(missing or mismatch or extra)}

def live_map(snapshot,now):
 validate_snapshot(snapshot)
 return {(x['db'],x['key_b64']):x for x in snapshot['entries']if x['expires_ms']==-1 or x['expires_ms']>now}

def reconcile_snapshot(client,s,before,apply=False):
 """Offline reverse mirror only: explicit frozen source + reviewed old-destination backup."""
 validate_snapshot(s);validate_snapshot(before)
 current=export_snapshot(client,False);now=client.now_ms();old=live_map(before,now);actual=live_map(current,now);desired=live_map(s,now)
 if old!=actual:raise ValueError('Rollback destination changed since reviewed snapshot')
 remove=sorted(set(actual)-set(desired));write=[x for k,x in desired.items()if actual.get(k)!=x]
 out={'dry_run':not apply,'restore_or_replace':len(write),'delete_stale':len(remove)}
 if not apply:return out
 if not s['consistent']:raise ValueError('Reverse source must be globally fenced')
 for db,key in remove:client.cmd('SELECT',db);client.cmd('DEL',base64.b64decode(key))
 for x in write:
  if x['expires_ms']!=-1 and x['expires_ms']<=client.now_ms():continue
  client.cmd('SELECT',x['db']);args=['RESTORE',base64.b64decode(x['key_b64']),0 if x['expires_ms']==-1 else x['expires_ms'],base64.b64decode(x['dump_b64']),'REPLACE']
  if x['expires_ms']!=-1:args.append('ABSTTL')
  client.cmd(*args)
 out['verification']=verify_snapshot(client,s)
 if not out['verification']['pass']:raise ValueError('Reverse mirror verification failed; remain fenced')
 return out


def validate_connection(cfg):
 if cfg.get('host')=='bj-crs-3dli07u2.sql.tencentcdb.com':
  if not cfg.get('tls') or not cfg.get('ca_file') or cfg.get('port')!=23136:raise ValueError('Pinned public endpoint requires verified TLS and CA file')
 return cfg

def check_clocks(a,b,max_skew_ms=2000):
 start=a.now_ms();peer=b.now_ms();end=a.now_ms()
 # Conservative bound includes round-trip latency; a slow sample also fails closed.
 skew=max(abs(start-peer),abs(peer-end))
 if skew>max_skew_ms:raise ValueError('Redis clock skew exceeds two seconds')
 return {'clock_difference_upper_bound_ms':skew,'sampling_interval_ms':end-start,'limit_ms':max_skew_ms,'pass':True}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['export','restore','verify','inventory','reconcile','clocks']);p.add_argument('--connection');p.add_argument('--source-running-container',action='store_true');p.add_argument('--snapshot');p.add_argument('--output');p.add_argument('--apply',action='store_true');p.add_argument('--frozen-receipt');p.add_argument('--before-snapshot');p.add_argument('--peer-connection');args=p.parse_args();os.umask(0o077)
 cfg=validate_connection(old_config()if args.source_running_container else private_json(args.connection))
 if args.apply and args.command not in ['restore','reconcile']:raise ValueError('Apply is restore-only')
 if args.command in ['restore','reconcile']and args.apply:
  expected='bj-crs-3dli07u2.sql.tencentcdb.com'if args.command=='restore'else'r-2zegjo7i4al4sh8q83pd.redis.rds.aliyuncs.com'
  if cfg['host']!=expected:raise ValueError('Unexpected restore direction')
  if not args.frozen_receipt:raise ValueError('Global writer fence receipt required')
  frozen_receipt(args.frozen_receipt,json.loads(Path(args.snapshot).read_text())['source_host'])
 r=Redis(cfg)
 try:
  if args.command=='clocks':
   peer=Redis(validate_connection(private_json(args.peer_connection)))
   try:print(json.dumps(check_clocks(r,peer)))
   finally:peer.close()
   return
  if args.command=='inventory':
   counts={}
   for db in DBS:r.cmd('SELECT',db);counts[str(db)]=r.cmd('DBSIZE')
   info=r.info();print(json.dumps({'dbsize':counts,'used_memory':info.get('used_memory'),'maxmemory':info.get('maxmemory'),'policy':info.get('maxmemory_policy'),'tls':r.tls}));return
  if args.command=='export':
   consistent=False
   if args.frozen_receipt:frozen_receipt(args.frozen_receipt,cfg['host']);consistent=True
   s=export_snapshot(r,consistent);s['source_host']=cfg['host'];save_private(args.output,s);print(json.dumps({'keys':len(s['entries']),'dump_bytes':s['dump_bytes'],'consistent':consistent,'sha256':s['sha256']}));return
  s=validate_snapshot(private_json(args.snapshot))
  if args.command=='restore':print(json.dumps(restore_snapshot(r,s,args.apply)))
  elif args.command=='reconcile':print(json.dumps(reconcile_snapshot(r,s,private_json(args.before_snapshot),args.apply)))
  else:
   result=verify_snapshot(r,s);print(json.dumps(result))
   if not result['pass']:raise SystemExit(2)
 finally:r.close()
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'status':'failed','error_type':type(e).__name__}));raise SystemExit(1)from None
