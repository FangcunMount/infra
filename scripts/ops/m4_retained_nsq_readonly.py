import json,subprocess,hashlib,stat,datetime,os,sys
from pathlib import Path
a=json.load(sys.stdin);D=['/usr/bin/docker','--host','unix:///var/run/docker.sock'];names=['nsqd','nsqlookupd','nsqadmin']
def inspect():
 p=subprocess.run(D+['ps','-aq'],capture_output=True,timeout=15);assert p.returncode==0
 p=subprocess.run(D+['inspect',*p.stdout.decode().split()],capture_output=True,timeout=20);assert p.returncode==0
 return json.loads(p.stdout)
def runtime(xs):return {x['Name']:[x['Id'],x['Image'],x['State']['Running'],x['State']['StartedAt'],x['RestartCount'],x['State'].get('OOMKilled')] for x in xs}
xs=inspect();before=runtime(xs);rows=[]
for x in xs:
 n=x['Name'].lstrip('/')
 if n not in names:continue
 old=next(r for r in a['NSQ']if r['name']==n)
 assert x['Id']==old['id'] and x['Mounts']==old['mounts']
 assert not x['State']['Running'] and x['HostConfig']['RestartPolicy']['Name']=='no'
 rows.append(dict(name=n,id_sha256=hashlib.sha256(x['Id'].encode()).hexdigest(),image_id=x['Image'],running=False,restart='no',original_mounts_preserved=True))
assert len(rows)==3
base=Path('/data/infra/nsq/data');assert base.is_dir() and not base.is_symlink();entries=[]
for p in sorted(base.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  s=p.stat();h=hashlib.sha256()
  with p.open('rb')as f:
   for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
  after=p.stat();assert os.path.samestat(s,after)and s.st_size==after.st_size and s.st_mtime_ns==after.st_mtime_ns
  entries.append(dict(path=str(p.relative_to(base)),bytes=s.st_size,sha256=h.hexdigest()))
assert entries==a['data_manifest'] and len(entries)==1519
for name,digest in a['config_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
backup=Path('/var/lib/fangcun-m3/windows/20261025081841-2/T35-retirement');b=backup/'pre-state.private.json'
assert b.is_file() and not b.is_symlink() and stat.S_IMODE(b.stat().st_mode)==0o600
archived=json.loads(b.read_bytes());assert archived['data_manifest']==entries
originals=[]
for p in sorted(backup.glob('*-original.private.bytes')):
 assert p.is_file() and not p.is_symlink() and stat.S_IMODE(p.stat().st_mode)==0o600
 originals.append(dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
assert len(originals)==3
p=subprocess.run(['ss','-Htan'],capture_output=True,timeout=15);assert p.returncode==0
for line in p.stdout.decode().splitlines():
 f=line.split()
 if len(f)>=5 and f[0]!='TIME-WAIT':assert f[3].rsplit(':',1)[-1]not in ['4150','4151','4160','4161','4171']and f[4].rsplit(':',1)[-1]not in ['4150','4151','4160','4161','4171']
assert runtime(inspect())==before
print(json.dumps(dict(schema='m4-c07-readonly-retained-assets/v1',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),containers=rows,data_files=1519,data_bytes=sum(x['bytes']for x in entries),data_tree_sha256=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest(),config_sha256=a['config_sha256'],source_backups=originals,pre_state_sha256=hashlib.sha256(b.read_bytes()).hexdigest(),nsq_listeners_and_connections=0,all_container_runtime_unchanged_during_read=True,read_only=True,production_changed=False)))
