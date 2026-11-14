#!/usr/bin/env python3
"""Disposable Grafana org isolation; no production credentials or users."""
import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

name='ai-grafana-test-'+uuid.uuid4().hex[:8]
password=uuid.uuid4().hex
try:
    subprocess.run(['docker','run','-d','--name',name,'-p','127.0.0.1::3000',
        '-e','GF_SECURITY_ADMIN_PASSWORD='+password,'-e','GF_AUTH_ANONYMOUS_ENABLED=false',
        'grafana/grafana:11.1.4'],check=True,stdout=subprocess.DEVNULL)
    port=subprocess.check_output(['docker','port',name,'3000/tcp'],text=True).strip().split(':')[-1]
    base='http://127.0.0.1:'+port
    def call(path,data=None,user='admin',org=None):
        headers={'Content-Type':'application/json'}
        if user:headers['Authorization']='Basic '+base64.b64encode((user+':'+password).encode()).decode()
        if org:headers['X-Grafana-Org-Id']=str(org)
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,{}
    for _ in range(60):
        try:
            if call('/api/health')[0]==200:break
        except OSError:pass
        time.sleep(1)
    code,body=call('/api/orgs',{'name':'AI Operations'});assert code==200
    org=body['orgId']
    assert call('/api/datasources',{'name':'AI logs','uid':'ai-logs','type':'loki','access':'proxy','url':'http://loki:3100'},org=org)[0]==200
    assert call('/api/admin/users',{'name':'General viewer','login':'viewer','email':'viewer@example.test','password':password})[0]==200
    assert call('/api/datasources/uid/ai-logs',org=org)[0]==200
    assert call('/api/datasources/uid/ai-logs',user='viewer')[0] in (403,404)
    assert call('/api/datasources/uid/ai-logs',user='viewer',org=org)[0] in (403,404)
    assert call('/api/datasources/uid/ai-logs',user=None)[0] in (401,403)
    print('PASS: ops datasource visible to admin; general user and anonymous denied')
finally:
    subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
