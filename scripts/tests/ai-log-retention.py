#!/usr/bin/env python3
"""Validate 14-day retention using synthetic old timestamps, isolated storage."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import urllib.parse
import uuid

root=Path(__file__).resolve().parents[2]/'components/ai-logging'
name='ai-retention-test-'+uuid.uuid4().hex[:8]
def run(*cmd):return subprocess.check_output(cmd,text=True).strip()
def wait(check,seconds=180):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            if check():return
        except (OSError,ValueError):pass
        time.sleep(2)
    raise AssertionError('retention condition timed out')
with tempfile.TemporaryDirectory(prefix=name) as directory:
    temp=Path(directory);data=temp/'data';data.mkdir();data.chmod(0o777)
    config=(root/'loki.yaml').read_text().replace('retention_delete_delay: 2h','retention_delete_delay: 1s\n  compaction_interval: 5s').replace('retention_period: 336h','retention_period: 0s').replace('limits_config:','limits_config:\n  reject_old_samples: false')
    (temp/'loki.yaml').write_text(config)
    try:
        run('docker','run','-d','--name',name,'-p','127.0.0.1::3100','-v',f'{data}:/loki','-v',f'{temp}/loki.yaml:/etc/loki/config.yaml:ro','grafana/loki:3.6.0','-config.file=/etc/loki/config.yaml')
        base='http://127.0.0.1:'+run('docker','port',name,'3100/tcp').split(':')[-1]
        wait(lambda:urllib.request.urlopen(base+'/ready',timeout=2).status==200)
        now=time.time_ns();old=now-15*24*3600*10**9
        payload={'streams':[{'stream':{'service':'retention-test','age':age},'values':[[str(ts),'retention-'+age]]} for age,ts in [('old',old),('current',now)]]}
        req=urllib.request.Request(base+'/loki/api/v1/push',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        assert urllib.request.urlopen(req,timeout=5).status==204
        def query(age,ts):
            q=urllib.parse.urlencode({'query':'{service="retention-test",age="'+age+'"}','start':str(ts-10**9),'end':str(ts+10**9)})
            result=json.load(urllib.request.urlopen(base+'/loki/api/v1/query_range?'+q,timeout=5))
            return sum(len(s['values']) for s in result['data']['result'])
        urllib.request.urlopen(urllib.request.Request(base+'/flush',data=b''),timeout=30).read()
        wait(lambda:query('old',old)==1 and query('current',now)==1,seconds=90)
        print('PASS: old and current fixtures initially queryable',flush=True)
        urllib.request.urlopen(urllib.request.Request(base+'/flush',data=b''),timeout=30).read()
        def chunks():
            return [p for p in (data/'chunks'/'fake').rglob('*') if p.is_file()]
        wait(lambda:len(chunks()) >= 2,seconds=60)
        before=len(chunks())
        run('docker','stop',name)
        (temp/'loki.yaml').write_text(config.replace('retention_period: 0s','retention_period: 336h'))
        run('docker','start',name)
        base='http://127.0.0.1:'+run('docker','port',name,'3100/tcp').split(':')[-1]
        wait(lambda:urllib.request.urlopen(base+'/ready',timeout=2).status==200)
        wait(lambda:len(chunks()) < before and query('old',old)==0 and query('current',now)==1,seconds=240)
        print('PASS: 15-day fixture expired; current fixture retained',flush=True)
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
