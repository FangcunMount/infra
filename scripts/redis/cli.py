#!/usr/bin/env python3
"""Read-only status adapter with explicit CA + hostname verification.

Uses existing REDIS_* environment bindings; supports only audited read commands.
"""
import argparse,os,sys
from resp import Redis
CA='/data/infra/ssl/redis/ca-chain.pem'
ALLOWED={'PING','INFO','DBSIZE','TTL','PTTL','ZCARD','TYPE'}

def config(env):
 tls=env.get('REDIS_USE_SSL','false')=='true';host=env['REDIS_HOST']
 if host.endswith('.sql.tencentcdb.com')and not tls:raise ValueError('Public Tencent Redis requires TLS')
 if (env.get('REDIS_SSL_INSECURE_SKIP_VERIFY')or 'false')!='false':raise ValueError('Certificate verification cannot be disabled')
 return {'host':host,'port':int(env.get('REDIS_PORT')or 6379),'username':env.get('REDIS_USERNAME',''),'password':env.get('REDIS_PASSWORD',''),'tls':tls,'ca_file':CA if tls else None}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('-n','--db',type=int,default=0);p.add_argument('--scan',action='store_true');p.add_argument('--count',type=int,default=200);p.add_argument('--pattern');p.add_argument('command',nargs='*');a=p.parse_args()
 if not 0<=a.db<256 or not 1<=a.count<=1000:raise ValueError('DB/count outside bounded inventory scope')
 if not a.scan and(not a.command or a.command[0].upper()not in ALLOWED):raise ValueError('Only audited read commands are supported')
 if a.scan and a.command:raise ValueError('SCAN cannot be combined with another command')
 r=Redis(config(os.environ))
 try:
  r.cmd('SELECT',a.db)
  if a.scan:
   cursor=b'0';scanned=0
   while True:
    args=['SCAN',cursor,'COUNT',a.count]
    if a.pattern:args.extend(['MATCH',a.pattern])
    cursor,keys=r.cmd(*args);scanned+=len(keys)
    if scanned>10000:raise ValueError('Inventory exceeds reviewed key bound')
    for k in keys:sys.stdout.buffer.write(k+b'\n')
    if cursor==b'0':break
  else:
   value=r.cmd(*a.command)
   if isinstance(value,bytes):sys.stdout.buffer.write(value+b'\n')
   elif isinstance(value,int):print(value)
   elif value is None:print('')
   else:raise ValueError('Unexpected response shape')
 finally:r.close()
if __name__=='__main__':
 try:main()
 except Exception as e:print('Redis read-only CLI failed: '+type(e).__name__,file=sys.stderr);raise SystemExit(1)from None
