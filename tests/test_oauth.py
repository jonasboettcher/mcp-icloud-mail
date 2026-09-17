import asyncio
import base64
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from icloud_mail.auth import OAuthProvider, callback_origin, digest
from icloud_mail.config import Config
from icloud_mail.server import http_app

KEY = 'test-only-connector-key-' + 'a'*32


@pytest.fixture
def config(tmp_path):
    return Config(email='test@icloud.com', app_password='test-only', public_url='https://mail.example.org', login_key_hash=digest(KEY), state_dir=tmp_path)


@pytest.fixture
def client(config):
    with TestClient(http_app(config), base_url=config.public_url) as client:
        yield client


def register(client):
    response = client.post('/register', json={'client_name':'Integration test', 'redirect_uris':['https://chatgpt.com/test-callback'],
        'token_endpoint_auth_method':'none', 'grant_types':['authorization_code','refresh_token'],
        'response_types':['code'], 'scope':'mail:read mail:drafts'})
    assert response.status_code == 201, response.text
    return response.json()['client_id']


def login_page(client, client_id, scope='mail:read mail:drafts'):
    verifier = 'v'*64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    response = client.get('/authorize', params=dict(client_id=client_id, redirect_uri='https://chatgpt.com/test-callback',
        response_type='code', code_challenge=challenge, code_challenge_method='S256', state='original-state',
        resource='https://mail.example.org/mcp', scope=scope), follow_redirects=False)
    assert response.status_code == 302, response.text
    page = client.get(response.headers['location'])
    assert page.status_code == 200
    return page, verifier


def login(client, client_id, scope='mail:read mail:drafts'):
    page, verifier = login_page(client, client_id, scope)
    flow = re.search(r'name="flow" value="([^"]+)"', page.text)[1]
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post('/login', data={'flow':flow, 'csrf':csrf, 'key':KEY}, headers={'origin':'https://mail.example.org'}, follow_redirects=False)
    assert response.status_code == 303, response.text
    query = parse_qs(urlsplit(response.headers['location']).query)
    assert query['state'] == ['original-state']
    return dict(grant_type='authorization_code', client_id=client_id, code=query['code'][0],
                redirect_uri='https://chatgpt.com/test-callback', code_verifier=verifier, resource='https://mail.example.org/mcp')


def test_browser_login_headers_and_csrf(client):
    page, _ = login_page(client, register(client))
    # no-referrer makes browsers send Origin: null on native form POSTs.
    assert page.headers['referrer-policy'] == 'same-origin'
    # Chromium also checks form-action against the post-login redirect.
    assert "form-action 'self' https://chatgpt.com;" in page.headers['content-security-policy']
    cookie = page.headers['set-cookie']
    assert '__Host-icloud-login=' in cookie
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    form = {'flow': re.search(r'name="flow" value="([^"]+)"', page.text)[1],
            'csrf': re.search(r'name="csrf" value="([^"]+)"', page.text)[1], 'key': KEY}
    for origin in ['https://attacker.example', 'null']:
        assert client.post('/login', data=form, headers={'origin': origin}).status_code == 403
    assert client.post('/login', data=dict(form, csrf='wrong'),
                       headers={'origin': 'https://mail.example.org'}).status_code == 403
    response = client.post('/login', data=form, headers={'origin': 'https://mail.example.org'}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'].startswith('https://chatgpt.com/test-callback?')


def test_login_requires_browser_cookie(client):
    page, _ = login_page(client, register(client))
    form = {'flow': re.search(r'name="flow" value="([^"]+)"', page.text)[1],
            'csrf': re.search(r'name="csrf" value="([^"]+)"', page.text)[1], 'key': KEY}
    client.cookies.clear()
    assert client.post('/login', data=form, headers={'origin': 'https://mail.example.org'}).status_code == 403


@pytest.mark.parametrize('uri', ['https://*.example.org/callback', 'https://example.org;evil/callback',
                                'https://user@example.org/callback'])
def test_callback_cannot_inject_csp_sources(uri):
    with pytest.raises(ValueError):
        callback_origin(uri)


def rpc(client, token, method, params=None):
    return client.post('/mcp', headers={'Authorization':'Bearer '+token, 'Accept':'application/json, text/event-stream'},
        json={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})


def test_discovery_protection_and_host(client):
    response = client.post('/mcp', json={})
    assert response.status_code == 401
    assert 'resource_metadata=' in response.headers['www-authenticate']
    discovery = client.get('/.well-known/oauth-authorization-server').json()
    assert discovery['code_challenge_methods_supported'] == ['S256']
    assert discovery['token_endpoint_auth_methods_supported'] == ['none', 'client_secret_post']
    assert discovery['registration_endpoint'].endswith('/register')
    resource = client.get('/.well-known/oauth-protected-resource/mcp').json()
    assert resource['resource'] == 'https://mail.example.org/mcp'
    assert set(resource['scopes_supported']) == {'mail:read', 'mail:drafts'}
    assert client.get('/login', headers={'host':'attacker.example'}).status_code == 400
    assert client.post('/login', data={'csrf':'bad','flow':'bad','key':KEY}).status_code == 403
    assert client.post('/login', content=b'x'*(1024*1024+1)).status_code == 413


def test_oauth_pkce_replay_refresh_and_revoke(client, config):
    cid = register(client)
    form = login(client, cid)
    wrong = client.post('/token', data=dict(form, code_verifier='x'*64))
    assert wrong.status_code == 400
    assert client.post('/token', data=dict(form, resource='https://evil.example/mcp')).status_code == 400
    response = client.post('/token', data=form)
    assert response.status_code == 200, response.text
    token = response.json()
    assert client.post('/token', data=form).status_code == 400
    init = rpc(client, token['access_token'], 'initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'test','version':'1'}})
    assert init.status_code == 200, init.text
    assert init.json()['result']['serverInfo']['name'] == 'iCloud Mail'
    listed = rpc(client, token['access_token'], 'tools/list').json()['result']['tools']
    assert {t['name'] for t in listed} == {'list_folders','search_messages','read_message','read_attachment','create_draft'}
    assert not next(t for t in listed if t['name']=='create_draft')['annotations']['readOnlyHint']
    # Tokens persist across restarts, while their plaintext never appears in storage.
    other = OAuthProvider(config)
    assert asyncio.run(other.load_access_token(token['access_token']))
    assert token['access_token'].encode() not in (config.state_dir/'oauth.sqlite3').read_bytes()
    refreshed = client.post('/token', data={'grant_type':'refresh_token','client_id':cid,'refresh_token':token['refresh_token']})
    assert refreshed.status_code == 200
    assert client.post('/token', data={'grant_type':'refresh_token','client_id':cid,'refresh_token':token['refresh_token']}).status_code == 400
    new = refreshed.json()
    revoked = client.post('/revoke', data={'client_id':cid, 'token':new['refresh_token'], 'token_type_hint':'refresh_token'})
    assert revoked.status_code == 200, revoked.text
    assert rpc(client, new['access_token'], 'tools/list').status_code == 401
    assert rpc(client, token['access_token'], 'tools/list').status_code == 401


def test_scope_enforcement_no_imap_needed(client, monkeypatch):
    from icloud_mail.mail import Mailbox
    monkeypatch.setattr(Mailbox, 'folders', lambda self: {'folders':[{'name':'INBOX','flags':[]}]})
    cid = register(client)
    form = login(client, cid, scope='mail:read')
    token = client.post('/token', data=form).json()['access_token']
    read = rpc(client, token, 'tools/call', {'name':'list_folders','arguments':{}}).json()['result']
    assert not read.get('isError')
    # Older MCP protocol versions expose the same JSON as text content.
    payload = read.get('structuredContent') or json.loads(read['content'][0]['text'])
    assert payload['folders'][0]['name'] == 'INBOX'
    response = rpc(client, token, 'tools/call', {'name':'create_draft','arguments':{
        'to':['test@example.org'],'subject':'s','body':'b','request_id':'request_0000000001'}})
    assert response.status_code == 200
    result = response.json()['result']
    assert result['isError'] is True
    assert 'mail:drafts' in result['content'][0]['text']


def test_invalid_registration_resource_and_origin(client):
    bad = client.post('/register', json={'redirect_uris':['http://evil.example/callback'],
        'grant_types':['authorization_code','refresh_token'], 'response_types':['code']})
    assert bad.status_code == 400
    cid = register(client)
    response = client.get('/authorize', params={'client_id':cid,'response_type':'code',
        'redirect_uri':'https://chatgpt.com/test-callback','code_challenge':'a'*43,'code_challenge_method':'S256',
        'resource':'https://evil.example/mcp'}, follow_redirects=False)
    assert response.status_code == 302
    assert 'error=invalid_request' in response.headers['location']


def test_rate_limit(client):
    for _ in range(30):
        client.get('/login')
    assert client.get('/login').status_code == 429


def test_attachment_tool_schema_and_upload(client, monkeypatch):
    import contextlib
    from email.parser import BytesParser
    from email.policy import default
    from icloud_mail.mail import Mailbox
    from test_mail import FakeIMAP
    imap = FakeIMAP()
    @contextlib.contextmanager
    def connection(self):
        yield imap
    monkeypatch.setattr(Mailbox, 'connection', connection)
    cid = register(client)
    token = client.post('/token', data=login(client, cid)).json()['access_token']
    listed = rpc(client, token, 'tools/list').json()['result']['tools']
    schema = next(t for t in listed if t['name'] == 'create_draft')['inputSchema']
    assert 'attachments' in schema['properties']
    assert 'content_base64' in json.dumps(schema)
    # Exercise the real authenticated MCP handler with a payload over the old 1 MiB limit.
    data = bytes(range(256)) * 4096
    arguments = dict(to=['p@example.org'], subject='File test', body='Attached', request_id='mcp_attachment_001',
                     attachments=[dict(filename='test.bin', content_base64=base64.b64encode(data).decode())])
    response = rpc(client, token, 'tools/call', {'name': 'create_draft', 'arguments': arguments})
    assert response.status_code == 200
    result = response.json()['result']
    assert not result.get('isError'), result
    parsed = BytesParser(policy=default).parsebytes(imap.saved)
    part = next(parsed.iter_attachments())
    assert part.get_payload(decode=True) == data
    assert part.get_content_type() == 'application/octet-stream'
    repeated = rpc(client, token, 'tools/call', {'name': 'create_draft', 'arguments': arguments}).json()['result']
    payload = repeated.get('structuredContent') or json.loads(repeated['content'][0]['text'])
    assert payload['reused']
    assert sum(c[0] == 'append' for c in imap.calls) == 1
    assert client.post('/mcp', content=b'x'*(16*1024*1024+1)).status_code == 413
