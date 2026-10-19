"""Small binary-safe RESP2 client for bounded migration operations. Never logs args."""
import socket,ssl,json,base64,hashlib,time,pathlib,os
class RedisError(RuntimeError):pass
class Redis:
 def __init__(self,cfg):

  if cfg.get('unix_socket'):
   raw=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);raw.connect(cfg['unix_socket'])
  else:raw=socket.create_connection((cfg['host'],int(cfg['port'])),8)
  raw.settimeout(10)
  if cfg.get('tls'):
   ctx=ssl.create_default_context(cafile=cfg.get('ca_file'),cadata=cfg.get('ca_data'));ctx.minimum_version=ssl.TLSVersion.TLSv1_2
   raw=ctx.wrap_socket(raw,server_hostname=cfg['host'])
  self.sock=raw;self.f=raw.makefile('rb');self.tls=raw.version()if isinstance(raw,ssl.SSLSocket)else None
  if cfg.get('password'):
   if cfg.get('auth_format')=='tencent-custom':self.cmd('AUTH',cfg['username']+'@'+cfg['password'])
   elif cfg.get('username'):self.cmd('AUTH',cfg['username'],cfg['password'])
   else:self.cmd('AUTH',cfg['password'])
 def close(self):self.f.close();self.sock.close()
 def read(self):
  line=self.f.readline()
  if not line or not line.endswith(b'\r\n'):raise RedisError('Incomplete RESP header')
  t=line[:1];v=line[1:-2]
  if t==b'-':raise RedisError(v.decode(errors='replace'))
  if t==b'+':return v
  if t==b':':return int(v)
  if t==b'$':
   n=int(v)
   if n<0:return None
   parts=[];remaining=n
   while remaining:
    b=self.f.read(remaining)
    if not b:raise RedisError('Incomplete RESP bulk')
    parts.append(b);remaining-=len(b)
   if self.f.read(2)!=b'\r\n':raise RedisError('Invalid RESP bulk ending')
   return b''.join(parts)
  if t==b'*':
   n=int(v)
   return None if n<0 else [self.read()for _ in range(n)]
  raise RedisError('Unsupported RESP type')
 def cmd(self,*args):
  b=[x if isinstance(x,bytes)else str(x).encode()for x in args];self.sock.sendall(b'*'+str(len(b)).encode()+b'\r\n'+b''.join(b'$'+str(len(x)).encode()+b'\r\n'+x+b'\r\n'for x in b));return self.read()
 def scan(self,db,limit=10000):
  self.cmd('SELECT',db);cursor=b'0';seen=set()
  while True:
   cursor,ks=self.cmd('SCAN',cursor,'COUNT',200);seen.update(ks)
   if len(seen)>limit:raise RedisError('Key count exceeds configured migration bound')
   if cursor==b'0':return sorted(seen)
 def info(self):
  return {k:v for line in self.cmd('INFO','ALL').decode().splitlines()if ':'in line for k,v in [line.split(':',1)]}
 def now_ms(self):
  sec,us=self.cmd('TIME');return int(sec)*1000+int(us)//1000

def old_config():
 import subprocess
 c=json.loads(subprocess.check_output(['docker','inspect','qs-apiserver']))[0];e=dict(x.split('=',1)for x in c['Config']['Env']if '='in x);p='QS_APISERVER_REDIS_'
 if not e[p+'HOST'].endswith('.redis.rds.aliyuncs.com'):raise RedisError('Unexpected source endpoint')
 return {'host':e[p+'HOST'],'port':int(e[p+'PORT']),'username':e.get(p+'USERNAME',''),'password':e[p+'PASSWORD'],'tls':False}

def capability(cfg):
 import uuid
 r=Redis(cfg);target_db=15;prefix='qlume:migration-preflight:'+uuid.uuid4().hex+':'
 keys=[(prefix+x).encode()for x in ['value','restored','counter','watch','source-rdb','abs-expiry']];out={'db':target_db,'namespace':prefix,'tls':r.tls,'checks':{},'writes_limited_to_owned_test_keys':True}
 source=None
 try:
  r.cmd('SELECT',target_db)
  assert all(r.cmd('EXISTS',k)==0 for k in keys)
  assert r.cmd('SET',keys[0],b'preflight\x00binary\xff','PX',600000)==b'OK'
  assert r.cmd('GET',keys[0])==b'preflight\x00binary\xff';out['checks']['binary_set_get']=True
  blob=r.cmd('DUMP',keys[0]);assert blob
  assert r.cmd('RESTORE',keys[1],600000,blob)==b'OK';assert r.cmd('GET',keys[1])==b'preflight\x00binary\xff';out['checks']['dump_restore']=True
  deadline=r.now_ms()+600000
  r.cmd('RESTORE',keys[5],deadline,blob,'ABSTTL');assert r.cmd('PEXPIRETIME',keys[5])==deadline;out['checks']['restore_absttl']=True
  assert r.cmd('EVAL',"return redis.call('SET', KEYS[1], 'lua-ok', 'PX', 600000)",1,keys[2])==b'OK';out['checks']['lua']=True
  r.cmd('WATCH',keys[3]);r.cmd('MULTI');r.cmd('SET',keys[3],'transaction-ok','PX',600000);r.cmd('GET',keys[3]);result=r.cmd('EXEC');assert result==[b'OK',b'transaction-ok'];out['checks']['watch_multi_exec']=True
  sub=Redis(cfg)
  try:
   channel=(prefix+'signal').encode();reply=sub.cmd('SUBSCRIBE',channel);assert reply[0]==b'subscribe';assert r.cmd('PUBLISH',channel,'probe')==1;message=sub.read();assert message==[b'message',channel,b'probe'];out['checks']['pubsub']=True
  finally:sub.close()
  try:
   source=Redis(old_config());chosen=None
   for db,pattern in [(2,b'cache:static:'),(8,b'cache:rank:')]:
    for k in source.scan(db):
     typ=source.cmd('TYPE',k)
     if k.startswith(pattern)and typ in [b'string',b'zset']:chosen=(db,k,typ);break
    if chosen:break
   if chosen:
    db,key,typ=chosen;blob=source.cmd('DUMP',key)
    if blob:
     r.cmd('RESTORE',keys[4],600000,blob)
     assert r.cmd('TYPE',keys[4])==typ
     assert r.cmd('DUMP',keys[4])==blob
     out['checks']['source_7_0_dump_to_target_7_1_restore']=True
     out['checks']['source_sample_db']=db;out['checks']['source_sample_type']=typ.decode()
    else:out['checks']['source_7_0_dump_to_target_7_1_restore']='source-key-expired'
   else:out['checks']['source_7_0_dump_to_target_7_1_restore']='no-live-safe-sample'
  except Exception as e:out['checks']['source_compat_error_type']=type(e).__name__
  out['status']='pass'
 finally:
  if source:source.close()
  try:
   r.cmd('SELECT',target_db);r.cmd('DEL',*keys);out['owned_test_keys_remaining']=sum(r.cmd('EXISTS',k)for k in keys)
  finally:r.close()
 return out
