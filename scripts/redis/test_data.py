import unittest.mock
import unittest,tempfile,subprocess,time,json,hashlib,copy,sys
from pathlib import Path
from resp import Redis,RedisError
from data import export_snapshot,restore_snapshot,verify_snapshot,validate_snapshot,digest,reconcile_snapshot,validate_connection,check_clocks
from runtime import payload,DEST

class Server:
 def __init__(self,policy='noeviction',maxmem='0'):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.sock=self.root/'r.sock'
  self.p=subprocess.Popen(['redis-server','--port','0','--unixsocket',str(self.sock),'--save','','--appendonly','no','--dir',str(self.root),'--maxmemory',maxmem,'--maxmemory-policy',policy],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  # Busy shared runners can defer the child well beyond two seconds.
  deadline=time.monotonic()+15
  while not self.sock.exists() and self.p.poll()is None and time.monotonic()<deadline:time.sleep(.05)
  try:
   if not self.sock.exists()or self.p.poll()is not None:raise RuntimeError('Isolated Redis startup deadline exceeded')
   self.r=Redis({'unix_socket':str(self.sock)})
   if self.r.cmd('PING')!=b'PONG':raise RuntimeError('Isolated Redis not ready')
  except Exception:
   if self.p.poll()is None:self.p.terminate();self.p.wait(timeout=4)
   self.tmp.cleanup();raise
 def close(self):
  self.r.close();self.p.terminate();self.p.wait(timeout=4);self.tmp.cleanup()

class DataContracts(unittest.TestCase):
 def setUp(self):self.a=Server();self.b=Server()
 def tearDown(self):self.a.close();self.b.close()
 def test_binary_multidb_ttl_and_persistent_roundtrip(self):
  for db in [0,8]:
   self.a.r.cmd('SELECT',db);self.a.r.cmd('SET',b'private\x00key',b'\x00\xffpayload','PX',60000);self.a.r.cmd('ZADD','persistent-rank',3,'member')
  snapshot=export_snapshot(self.a.r,True);self.assertEqual(len(snapshot['entries']),4)
  self.assertTrue(restore_snapshot(self.b.r,snapshot)['dry_run']);self.b.r.cmd('SELECT',0);self.assertEqual(self.b.r.cmd('DBSIZE'),0)
  self.assertEqual(restore_snapshot(self.b.r,snapshot,True)['restored'],4);self.assertTrue(verify_snapshot(self.b.r,snapshot)['pass'])
 def test_expired_auth_state_is_not_resurrected(self):
  self.a.r.cmd('SET','auth-token','sample','PX',60);s=export_snapshot(self.a.r,True);time.sleep(.1);out=restore_snapshot(self.b.r,s,True);self.assertEqual(out['restored'],0);self.assertEqual(out['expired_skipped'],1)
 def test_live_backup_cannot_be_applied(self):
  self.a.r.cmd('SET','auth','value');s=export_snapshot(self.a.r,False)
  with self.assertRaises(ValueError):restore_snapshot(self.b.r,s,True)
 def test_nonempty_target_is_never_overwritten(self):
  self.a.r.cmd('SET','auth','new');self.b.r.cmd('SET','auth','existing');s=export_snapshot(self.a.r,True)
  with self.assertRaises(ValueError):restore_snapshot(self.b.r,s,True)
  self.assertEqual(self.b.r.cmd('GET','auth'),b'existing')
 def test_corruption_and_extra_keys_fail_verification(self):
  self.a.r.cmd('SET','auth','value');s=export_snapshot(self.a.r,True);broken=copy.deepcopy(s);broken['entries'][0]['dump_b64']='Yg=='
  with self.assertRaises(ValueError):validate_snapshot(broken)
  restore_snapshot(self.b.r,s,True);self.b.r.cmd('SELECT',4);self.b.r.cmd('SET','unexpected','value');self.assertFalse(verify_snapshot(self.b.r,s)['pass'])

class ReverseMirrorContracts(unittest.TestCase):
 def setUp(self):self.new=Server();self.old=Server()
 def tearDown(self):self.new.close();self.old.close()
 def test_latest_auth_state_wins_and_stale_keys_are_removed_only_with_explicit_apply(self):
  self.new.r.cmd('SET','auth:current','new','PX',60000);self.old.r.cmd('SET','auth:current','stale');self.old.r.cmd('SET','revoked-old-session','stale')
  source=export_snapshot(self.new.r,True);before=export_snapshot(self.old.r,False)
  plan=reconcile_snapshot(self.old.r,source,before);self.assertEqual(plan['delete_stale'],1);self.assertEqual(plan['restore_or_replace'],1)
  self.old.r.cmd('SELECT',0);self.assertEqual(self.old.r.cmd('GET','auth:current'),b'stale')
  result=reconcile_snapshot(self.old.r,source,before,True);self.assertTrue(result['verification']['pass'])
 def test_destination_drift_blocks_reverse_mirror(self):
  source=export_snapshot(self.new.r,True);before=export_snapshot(self.old.r,False);self.old.r.cmd('SET','unexpected','new-writer')
  with self.assertRaises(ValueError):reconcile_snapshot(self.old.r,source,before,True)
  self.assertEqual(self.old.r.cmd('GET','unexpected'),b'new-writer')
 def test_unfenced_reverse_source_is_rejected(self):
  source=export_snapshot(self.new.r,False);before=export_snapshot(self.old.r,False)
  with self.assertRaises(ValueError):reconcile_snapshot(self.old.r,source,before,True)

class EvictionContracts(unittest.TestCase):
 def test_noeviction_rejects_growth_but_preserves_existing_state_and_reads(self):
  s=Server('noeviction','2mb')
  try:
   s.r.cmd('SET','auth-session','kept');rejected=False
   for n in range(100):
    try:s.r.cmd('SET','filler:'+str(n),b'x'*65536)
    except RedisError:rejected=True;break
   self.assertTrue(rejected);self.assertEqual(s.r.cmd('GET','auth-session'),b'kept');self.assertEqual(s.r.cmd('DEL','filler:0'),1)
  finally:s.close()
 def test_allkeys_lru_can_evict_nonexpiring_auth_state_across_db_boundaries(self):
  s=Server('allkeys-lru','2mb')
  try:
   for n in range(100):s.r.cmd('SET','auth:'+str(n),'protected-business-state')
   s.r.cmd('SELECT',2)
   for n in range(200):s.r.cmd('SET','cache:'+str(n),b'x'*65536)
   s.r.cmd('SELECT',0);remaining=s.r.cmd('DBSIZE');self.assertLess(remaining,100);self.assertGreater(int(s.r.info()['evicted_keys']),0)
  finally:s.close()

class RuntimeAllowlist(unittest.TestCase):
 def before(self):return {'Name':'/iam-apiserver','Id':'a'*64,'Image':'sha256:'+'b'*64,'Config':{'Env':['IAM_APISERVER_REDIS_CACHE_HOST=r-2zegjo7i4al4sh8q83pd.redis.rds.aliyuncs.com','IAM_APISERVER_REDIS_CACHE_PORT=16380','IAM_APISERVER_REDIS_CACHE_DATABASE=0','IAM_APISERVER_REDIS_CACHE_USE_SSL=false','IAM_APISERVER_REDIS_CACHE_PASSWORD=old-secret','IAM_APISERVER_MYSQL_HOST=keep-db:3306','GOMEMLIMIT=256MiB'],'Image':'old-tag','Labels':{'business':'keep'}},'HostConfig':{'Binds':['/keep:/app/configs:ro'],'Memory':12345,'RestartPolicy':{'Name':'unless-stopped'}},'NetworkSettings':{'Networks':{'infra-network':{'Aliases':['iam-apiserver','a'*12,'a'*64]}}}}
 def test_mysql_resources_images_and_aliases_are_preserved(self):
  b=self.before();t={'host':'bj-crs-3dli07u2.sql.tencentcdb.com','port':23136,'username':'app','password':'literal$secret'};out=payload(b,t,'c'*64);env=dict(x.split('=',1)for x in out['Env'])
  self.assertEqual(out['Image'],b['Image']);self.assertEqual(out['HostConfig']['Memory'],12345);self.assertEqual(env['IAM_APISERVER_MYSQL_HOST'],'keep-db:3306');self.assertEqual(env['IAM_APISERVER_REDIS_CACHE_PASSWORD'],'app@literal$secret');self.assertEqual(env['IAM_APISERVER_REDIS_CACHE_USERNAME'],'');self.assertEqual(out['NetworkingConfig']['EndpointsConfig']['infra-network']['Aliases'],['iam-apiserver']);self.assertIn('/etc/ssl/certs',env['SSL_CERT_DIR']);self.assertEqual(b,self.before())
 def test_empty_and_static_ipam_metadata_are_preserved_exactly(self):
  b=self.before();b['NetworkSettings']['Networks']['infra-network']['IPAMConfig']={'IPv4Address':'','IPv6Address':''};t={'host':'bj-crs-3dli07u2.sql.tencentcdb.com','port':23136,'username':'app','password':'secret'}
  self.assertEqual(payload(b,t,'c'*64)['NetworkingConfig']['EndpointsConfig']['infra-network']['IPAMConfig'],{'IPv4Address':'','IPv6Address':''})
  b['NetworkSettings']['Networks']['infra-network']['IPAMConfig']['IPv4Address']='172.20.0.8'
  self.assertEqual(payload(b,t,'c'*64)['NetworkingConfig']['EndpointsConfig']['infra-network']['IPAMConfig']['IPv4Address'],'172.20.0.8')
 def test_unknown_container_and_db_drift_are_rejected(self):
  b=self.before();b['Name']='/miniblog-backend'
  with self.assertRaises(ValueError):payload(b,{},'c'*64)
  b=self.before();b['Config']['Env'][0]='IAM_APISERVER_REDIS_CACHE_DATABASE=5'
  with self.assertRaises(ValueError):payload(b,{'host':'bj-crs-3dli07u2.sql.tencentcdb.com','port':23136,'username':'app','password':'secret'},'c'*64)


class PreparationGuards(unittest.TestCase):
 def test_public_target_fails_closed_without_tls_or_ca(self):
  target={'host':'bj-crs-3dli07u2.sql.tencentcdb.com','port':23136,'tls':True,'ca_file':'/public/ca.pem'}
  self.assertEqual(validate_connection(target),target)
  for field,value in [('tls',False),('ca_file',''),('port',6379)]:
   with self.assertRaises(ValueError):validate_connection(dict(target,**{field:value}))
 def test_status_cli_rejects_skipverify_and_plaintext(self):
  from cli import config
  env={'REDIS_HOST':'bj-crs-3dli07u2.sql.tencentcdb.com','REDIS_USE_SSL':'true'}
  self.assertTrue(config(env)['tls'])
  self.assertFalse(config({'REDIS_HOST':'localhost','REDIS_SSL_INSECURE_SKIP_VERIFY':''})['tls'])
  for extra in [{'REDIS_USE_SSL':'false'},{'REDIS_SSL_INSECURE_SKIP_VERIFY':'true'}]:
   with self.assertRaises(ValueError):config(dict(env,**extra))
 def test_clock_skew_gate(self):
  a=unittest.mock.Mock();b=unittest.mock.Mock();a.now_ms.side_effect=[10000,10020];b.now_ms.return_value=10010
  self.assertTrue(check_clocks(a,b)['pass'])
  a.now_ms.side_effect=[10000,10020];b.now_ms.return_value=13000
  with self.assertRaises(ValueError):check_clocks(a,b)
 def test_capability_cleanup_selects_target_db_after_source_db8_sample(self):
  from resp import capability
  old=Server();new=Server()
  try:
   old.r.cmd('SELECT',8);old.r.cmd('ZADD','cache:rank:sample',1,'synthetic')
   with unittest.mock.patch('resp.old_config',return_value={'unix_socket':str(old.sock)}):
    result=capability({'unix_socket':str(new.sock)})
   self.assertEqual(result['checks']['source_sample_db'],8)
   new.r.cmd('SELECT',15);self.assertEqual(new.r.cmd('DBSIZE'),0)
   old.r.cmd('SELECT',8);self.assertEqual(old.r.cmd('ZCARD','cache:rank:sample'),1)
  finally:old.close();new.close()

if __name__=='__main__':unittest.main()
