"""Install only mq virtual host on serverA, then exercise actual HTTPS login."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from acceptance import verify
from native_broker import digest,inspect,run

REPO=Path(__file__).resolve().parents[2]
HOST='mq.fangcunmount.cn'
TARGET=Path('/data/apps/nginx-configs/mq.fangcunmount.cn.conf')


def atomic(path,raw):
    temporary=path.with_name('.'+path.name+'.'+str(time.time_ns()))
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o644)
    os.fchmod(fd,0o644)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-nginx-id',required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    credentials=json.load(sys.stdin)
    if os.geteuid()!=0 or args.receipt.exists():raise RuntimeError('root_and_new_receipt_required')
    if '100.74.123.45' not in run(['tailscale','ip','-4']).stdout.split():raise RuntimeError('servera_identity_changed')
    with open('/var/lib/fangcun-image-retention/deploy.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=inspect('nginx')
        if before['Id']!=args.expected_nginx_id or not before['State']['Running']:
            raise RuntimeError('nginx_identity_changed')
        files={p.name:digest(p) for p in TARGET.parent.glob('*.conf')}
        if TARGET.exists():raise RuntimeError('mq_virtual_host_already_exists_verify_instead')
        raw=(REPO/'components/rocketmq-dashboard/server-a.conf').read_bytes()
        closed=(REPO/'components/rocketmq-dashboard/server-a-closed.conf').read_bytes()
        atomic(TARGET,raw)
        if run(['docker','exec','nginx','nginx','-t'],required=False).returncode:
            TARGET.unlink();raise RuntimeError('candidate_nginx_syntax_failed')
        try:
            run(['docker','exec','nginx','nginx','-s','reload'])
            # Preserve the real TLS SNI, Origin, cookies and certificate checks;
            # use loopback transport only for this host-local acceptance.
            resolve=socket.getaddrinfo
            def local_sni(host,port,*pos,**kw):
                return resolve('127.0.0.1' if host==HOST else host,port,*pos,**kw)
            socket.getaddrinfo=local_sni
            try:
                deadline=time.monotonic()+30
                while True:
                    try:cases=verify('https://'+HOST,credentials);break
                    except OSError:
                        if time.monotonic()>=deadline:raise
                        time.sleep(2)
            finally:socket.getaddrinfo=resolve
            after=inspect('nginx')
            cases.update(original_virtual_hosts_unchanged=all(digest(TARGET.parent/name)==value for name,value in files.items()),
                nginx_not_restarted=after['Id']==before['Id'] and after['State']['StartedAt']==before['State']['StartedAt'],
                exact_mq_virtual_host=digest(TARGET)==hashlib.sha256(raw).hexdigest())
            if not all(cases.values()):raise RuntimeError('https_ingress_acceptance_failed')
            receipt=dict(passed=len(cases),failed=0,skipped=0,cases=cases,url='https://'+HOST,
                source_sha=REPO.name,nginx_id=after['Id'],virtual_host_sha256=digest(TARGET),
                certificate='/data/ssl/certs/fangcunmount.cn.crt',credentials_written_to_servera=False)
            args.receipt.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd=os.open(args.receipt,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump(receipt,stream,indent=2)
            print(json.dumps(receipt))
        except Exception:
            atomic(TARGET,closed)
            if run(['docker','exec','nginx','nginx','-t'],required=False).returncode==0:
                run(['docker','exec','nginx','nginx','-s','reload'],required=False)
            raise


if __name__=='__main__':main()
