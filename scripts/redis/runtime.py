#!/usr/bin/env python3
"""Prepare immutable-image Redis/TLS runtime plans. Does not start/stop containers.

Plans contain credentials: root-owned private directories only, never commit them.
"""
import argparse,copy,fcntl,hashlib,importlib.util,json,os,re,subprocess
from pathlib import Path
from urllib.parse import quote
spec=importlib.util.spec_from_file_location('mysql_runtime',Path(__file__).parents[1]/'mysql/runtime.py');docker=importlib.util.module_from_spec(spec);spec.loader.exec_module(docker)
CA='/data/infra/ssl/redis/ca-chain.pem';DEST='/etc/qlume/redis/ca-chain.pem';CA_DIR='/etc/qlume/redis'
PREFIXES={'qs-apiserver':'QS_APISERVER_REDIS_','iam-apiserver':'IAM_APISERVER_REDIS_CACHE_','qs-collection-server-1':'COLLECTION_SERVER_REDIS_','qs-collection-server-2':'COLLECTION_SERVER_REDIS_','qs-worker-runtime-1':'QS_WORKER_REDIS_','qs-worker-runtime-2':'QS_WORKER_REDIS_','qs-worker-runtime-3':'QS_WORKER_REDIS_'}

def payload(before,target,ca_hash):
 name=before['Name'].lstrip('/')
 if name not in PREFIXES:raise ValueError('Container outside approved Redis scope')
 if target['host']!='bj-crs-3dli07u2.sql.tencentcdb.com'or target['port']!=23136:raise ValueError('Unexpected verified Redis endpoint')
 if not target['username'] or not target['password']or not re.fullmatch('[0-9a-f]{64}',ca_hash):raise ValueError('Invalid credential/CA metadata')
 prefix=PREFIXES[name];config=copy.deepcopy(before['Config']);env=dict(x.split('=',1)for x in config['Env']);expected_db='0'if name=='iam-apiserver'else'1'
 if env.get(prefix+'HOST')!='r-2zegjo7i4al4sh8q83pd.redis.rds.aliyuncs.com' or env.get(prefix+'PORT')!='16380':raise ValueError('Unexpected source endpoint')
 if env.get(prefix+'DATABASE')!=expected_db or env.get(prefix+'ADDRESSES')or env.get(prefix+'ADDRS'):raise ValueError('Unexpected effective Redis route/DB')
 if env.get(prefix+'USE_SSL')!='false':raise ValueError('Source TLS state differs from baseline')
 roots=env.get('SSL_CERT_DIR')or'/etc/ssl/certs:/etc/pki/tls/certs'
 env.update({prefix+'HOST':target['host'],prefix+'PORT':str(target['port']),prefix+'USERNAME':'',prefix+'PASSWORD':target['username']+'@'+target['password'],prefix+'USE_SSL':'true',prefix+'SSL_INSECURE_SKIP_VERIFY':'false','SSL_CERT_DIR':roots+(''if CA_DIR in roots.split(':')else':'+CA_DIR),'QLUME_REDIS_CA_SHA256':ca_hash})
 config['Env']=[k+'='+v for k,v in env.items()];config['Image']=before['Image']
 hc=copy.deepcopy(before['HostConfig']);binds=hc.get('Binds')or[]
 if any(DEST==x.split(':')[1]for x in binds if ':'in x):raise ValueError('Redis CA mount already present')
 hc['Binds']=[*binds,CA+':'+DEST+':ro'];nets={}
 for n,v in before['NetworkSettings']['Networks'].items():
  nets[n]={k:copy.deepcopy(v[k])for k in ['IPAMConfig','DriverOpts']if v.get(k)is not None};nets[n]['Aliases']=[a for a in v.get('Aliases')or[]if a not in (before['Id'],before['Id'][:12])]
 return dict(config,HostConfig=hc,NetworkingConfig={'EndpointsConfig':nets})

def config_hashes(before):
 out={}
 for m in before['Mounts']:
  if not m['Destination'].startswith('/app/configs'):continue
  source=Path(m['Source']);files=[source]if source.is_file()else sorted(x for x in source.rglob('*')if x.is_file()and not x.is_symlink())
  for f in files:
   if f.stat().st_size>10*1024*1024:raise ValueError('Unexpected configuration file size')
   out[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
 return out

def plan(name,target,directory,manifest):
 before=docker.api('GET','/containers/'+quote(name,safe='')+'/json');image=docker.api('GET','/images/'+before['Image']+'/json')
 if image['Id']!=before['Image']:raise ValueError('Image identity mismatch')
 if hashlib.sha256(Path(CA).read_bytes()).hexdigest()!=manifest['ca_sha256']:raise ValueError('CA mismatch')
 result={'name':name,'before':before,'image_id':before['Image'],'ca_sha256':manifest['ca_sha256'],'target_host':target['host'],'target_port':target['port'],'source_host':dict(x.split('=',1)for x in before['Config']['Env'])[PREFIXES[name]+'HOST'],'config_hashes':config_hashes(before),'static_network_handoff':[n for n,e in before['NetworkSettings']['Networks'].items()if any((e.get('IPAMConfig')or{}).get(k)for k in ['IPv4Address','IPv6Address','LinkLocalIPs'])],'payload':payload(before,target,manifest['ca_sha256'])}
 docker.save(directory/'plan.json',result);return {'name':name,'image_id':before['Image'],'state':'prepared-not-applied','config_files':len(result['config_hashes'])}

def verify(directory,target,manifest):
 p=json.loads((directory/'plan.json').read_text());now=docker.api('GET','/containers/'+quote(p['name'],safe='')+'/json')
 if docker.stable(now)!=docker.stable(p['before'])or now['NetworkSettings']['Networks']!=p['before']['NetworkSettings']['Networks']or config_hashes(now)!=p['config_hashes']:raise ValueError('Production baseline changed; replan required')
 if p['payload']!=payload(p['before'],target,manifest['ca_sha256']):raise ValueError('Plan exceeds allowlist')
 if hashlib.sha256(Path(CA).read_bytes()).hexdigest()!=p['ca_sha256']:raise ValueError('CA changed')
 return {'name':p['name'],'state':'baseline-and-allowlist-verified','image_id':p['image_id']}

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('command',choices=['plan','verify']);a.add_argument('--name',choices=sorted(PREFIXES));a.add_argument('--directory',type=Path,required=True);a.add_argument('--target-file',type=Path,required=True);args=a.parse_args();os.umask(0o077)
 if args.target_file.is_symlink()or args.target_file.stat().st_mode & 0o077:raise ValueError('Private credential file required')
 args.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
 if args.directory.is_symlink()or args.directory.stat().st_mode & 0o077:raise ValueError('Private plan directory required')
 target=json.loads(args.target_file.read_text());manifest=json.loads((Path(__file__).parents[2]/'components/redis-client/manifest.json').read_text())
 lockpath=Path('/var/lib/fangcun-image-retention/deploy.lock');lockpath.parent.mkdir(parents=True,exist_ok=True)
 with lockpath.open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  print(json.dumps(plan(args.name,target,args.directory,manifest)if args.command=='plan'else verify(args.directory,target,manifest)))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'redis_runtime_prepare':'failed','error_type':type(e).__name__}));raise SystemExit(1)from None
