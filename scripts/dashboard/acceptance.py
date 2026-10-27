"""Read-only Dashboard authentication and inventory acceptance; no message bodies."""
import http.cookiejar
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def client(ca_file=None):
    jar=http.cookiejar.CookieJar()
    handlers=[urllib.request.HTTPCookieProcessor(jar),NoRedirect()]
    if ca_file:handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(ca_file))))
    session=urllib.request.build_opener(*handlers)
    session.cookies=jar
    return session


def request(session, base, path, data=None, *, csrf=True):
    body = None if data is None else json.dumps(data,separators=(',',':')).encode()
    headers={}
    if data is not None:
        headers['Content-Type']='application/json'
        headers['Origin']=base
        if csrf:
            status, token=request(session,base,'/rocketmq-dashboard/csrf-token')
            assert status==200 and token.get('data',{}).get('token'), 'csrf_bootstrap_failed'
            headers[token['data']['headerName']]=token['data']['token']
    req=urllib.request.Request(base+path,data=body,headers=headers)
    try:
        with session.open(req, timeout=20) as response:
            try: value=json.load(response)
            except ValueError: value={'non_json': True}
            return response.status, value
    except urllib.error.HTTPError as error:
        try: value=json.load(error)
        except ValueError: value={}
        if error.headers.get('Location'):value['redirect_location']=error.headers['Location']
        return error.code, value


def accepted(result):
    return result[0] == 200 and result[1].get('status') == 0


def origin(url):
    value=urllib.parse.urlsplit(url)
    return value.scheme,value.hostname,value.port or (443 if value.scheme=='https' else 80)


def verify(base, credentials, ca_file=None):
    session=client(ca_file)
    status, check=request(session,base,'/login/check.query')
    assert status==200 and check['data']['loginRequired'] and not check['data']['logined'], 'login_not_enforced'
    paths=['/cluster/list.query','/topic/list.query','/consumer/groupList.query']
    for path in paths:
        response=request(session,base,path)
        assert not accepted(response), 'anonymous_inventory_allowed'
        if 'redirect_location' in response[1]:
            target=urllib.parse.urljoin(base,response[1]['redirect_location'])
            assert origin(target)==origin(base), 'login_redirect_loses_public_origin'
    assert request(session,base,'/login/login.do',credentials,csrf=False)[0]==403, 'csrf_not_enforced'
    assert not accepted(request(session,base,'/login/login.do',dict(username='admin',password='admin'))), 'default_login_allowed'
    assert not accepted(request(session,base,'/login/login.do',dict(username=credentials['username'],password='incorrect'))), 'wrong_password_allowed'
    login=request(session,base,'/login/login.do',credentials)
    if not accepted(login):
        error=AssertionError('independent_login_failed')
        message=str(login[1].get('errMsg',''))
        redacted=message.replace(credentials['password'],'[redacted]')
        redacted=re.sub(r'\b[0-9a-fA-F]{32,}\b|\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b','[redacted]',redacted)
        error.diagnostics=dict(http_status=login[0],app_status=login[1].get('status'),
            response_fields=sorted(login[1]),
            error_message_redacted=redacted[:700],
            bad_credentials='Bad username or password' in message,
            error_classes=sorted(set(re.findall(r'\b[A-Za-z_][\w.]*(?:Exception|Error)\b',message))))
        raise error
    assert base.startswith('https://'), 'https_management_origin_required'
    assert any(c.name=='JSESSIONID' and c.secure and c.has_nonstandard_attr('HttpOnly')
        for c in session.cookies), 'secure_httponly_session_required'
    results={path:request(session,base,path) for path in paths}
    assert all(accepted(row) and row[1].get('data') for row in results.values()), 'authenticated_inventory_failed'
    # Only counts/booleans leave this function; no cluster/topic payloads.
    assert accepted(request(session,base,'/login/logout.do',{})), 'logout_failed'
    assert not accepted(request(session,base,paths[0])), 'logout_did_not_revoke_session'
    return dict(login_required=True,csrf_required=True,secure_https_session=True,
        anonymous_inventory_denied=True,default_login_denied=True,
        wrong_password_denied=True,independent_login=True,tls_authenticated_cluster=True,
        topics_read=True,consumer_groups_read=True,logout_revokes_session=True,
        no_message_mutations=True)
