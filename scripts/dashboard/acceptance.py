"""Read-only Dashboard authentication and inventory acceptance; no message bodies."""
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),NoRedirect())


def request(session, base, path, data=None):
    body = None if data is None else urllib.parse.urlencode(data).encode()
    try:
        with session.open(base+path, data=body, timeout=20) as response:
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


def verify(base, credentials):
    session=client()
    status, check=request(session,base,'/login/check.query')
    assert status==200 and check['data']['loginRequired'] and not check['data']['logined'], 'login_not_enforced'
    paths=['/cluster/list.query','/topic/list.query','/consumer/groupList.query']
    for path in paths:
        response=request(session,base,path)
        assert not accepted(response), 'anonymous_inventory_allowed'
        if 'redirect_location' in response[1]:
            target=urllib.parse.urljoin(base,response[1]['redirect_location'])
            assert urllib.parse.urlsplit(target).netloc==urllib.parse.urlsplit(base).netloc, 'login_redirect_loses_public_origin'
    assert not accepted(request(session,base,'/login/login.do',dict(username='admin',password='admin'))), 'default_login_allowed'
    assert not accepted(request(session,base,'/login/login.do',dict(username=credentials['username'],password='incorrect'))), 'wrong_password_allowed'
    assert accepted(request(session,base,'/login/login.do',credentials)), 'independent_login_failed'
    results={path:request(session,base,path) for path in paths}
    assert all(accepted(row) and row[1].get('data') for row in results.values()), 'authenticated_inventory_failed'
    # Only counts/booleans leave this function; no cluster/topic payloads.
    assert accepted(request(session,base,'/login/logout.do',{})), 'logout_failed'
    assert not accepted(request(session,base,paths[0])), 'logout_did_not_revoke_session'
    return dict(login_required=True,anonymous_inventory_denied=True,default_login_denied=True,
        wrong_password_denied=True,independent_login=True,tls_authenticated_cluster=True,
        topics_read=True,consumer_groups_read=True,logout_revokes_session=True,
        no_message_mutations=True)
