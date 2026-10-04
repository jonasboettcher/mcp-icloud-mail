import asyncio
import base64
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient
from lexware_gateway.server import Config, http_app
from lexware_gateway.auth import digest

KEY = 'test-only-' + 'x'*40

@pytest.fixture
def app(tmp_path):
    return http_app(Config('https://lexware.example.org', digest(KEY), tmp_path), configured=False)

@pytest.fixture
def client(app):
    with TestClient(app, base_url='https://lexware.example.org') as client:
        yield client

def connect(client, scope='lexware:read lexware:vouchers'):
    reg = client.post('/register', json={'client_name':'ChatGPT test',
        'redirect_uris':['https://chatgpt.com/test-callback'], 'token_endpoint_auth_method':'none',
        'grant_types':['authorization_code','refresh_token'], 'response_types':['code'], 'scope':scope})
    assert reg.status_code == 201, reg.text
    client_id = reg.json()['client_id']
    verifier = 'v'*64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    auth = client.get('/authorize', params=dict(client_id=client_id, redirect_uri='https://chatgpt.com/test-callback',
        response_type='code', code_challenge=challenge, code_challenge_method='S256', state='bound-state',
        resource='https://lexware.example.org/mcp', scope=scope), follow_redirects=False)
    assert auth.status_code == 302, auth.text
    page = client.get(auth.headers['location'])
    assert 'Lexware Office' in page.text
    assert "form-action 'self' https://chatgpt.com;" in page.headers['content-security-policy']
    form={'flow': re.search(r'name="flow" value="([^"]+)"', page.text)[1],
          'csrf': re.search(r'name="csrf" value="([^"]+)"', page.text)[1], 'key':KEY}
    assert client.post('/login',data=form,headers={'origin':'https://evil.example'}).status_code == 403
    login = client.post('/login', data=form, headers={'origin':'https://lexware.example.org'}, follow_redirects=False)
    assert login.status_code == 303, login.text
    query = parse_qs(urlsplit(login.headers['location']).query)
    assert query['state'] == ['bound-state']
    token_form = dict(grant_type='authorization_code', client_id=client_id, code=query['code'][0],
        redirect_uri='https://chatgpt.com/test-callback', code_verifier=verifier, resource='https://lexware.example.org/mcp')
    assert client.post('/token',data=dict(token_form,code_verifier='w'*64)).status_code == 400
    token = client.post('/token',data=token_form)
    assert token.status_code == 200, token.text
    assert client.post('/token',data=token_form).status_code == 400
    return client_id, token.json()

def test_oauth_and_missing_key_blocks_calls(client):
    assert client.post('/mcp',json={}).status_code == 401
    meta=client.get('/.well-known/oauth-protected-resource/mcp').json()
    assert meta['scopes_supported'] == ['lexware:read','lexware:vouchers']
    client_id, token=connect(client)
    result=client.post('/mcp',headers={'Authorization':'Bearer '+token['access_token']},json={
        'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'update-voucher','arguments':{'id':'test'}}})
    assert result.status_code == 200
    assert result.json()['result']['isError'] is True
    assert 'No Lexware request' in result.text
    assert client.post('/revoke',data={'client_id':client_id,'token':token['access_token']}).status_code == 200
    assert client.post('/mcp',headers={'Authorization':'Bearer '+token['access_token']},json={}).status_code == 401

def test_refresh_rotation_and_resource_binding(client):
    client_id, token=connect(client)
    form={'grant_type':'refresh_token','client_id':client_id,'refresh_token':token['refresh_token'],
          'resource':'https://evil.example/mcp'}
    assert client.post('/token',data=form).status_code == 400
    form['resource']='https://lexware.example.org/mcp'
    assert client.post('/token',data=form).status_code == 200
    assert client.post('/token',data=form).status_code == 400

def test_scope_and_body_limits(app, client):
    app.state.client = None
    _, token=connect(client,scope='lexware:read')
    # Enable calls for this isolated test, without any actual upstream request.
    configured_app=http_app(Config('https://lexware.example.org',digest(KEY),app.state.provider.config.state_dir),configured=True)
    with TestClient(configured_app,base_url='https://lexware.example.org') as c:
        response=c.post('/mcp',headers={'Authorization':'Bearer '+token['access_token']},json={
            'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'update-voucher','arguments':{}}})
        assert response.status_code == 403
        assert c.post('/mcp',content=b'x'*(16*1024*1024+1)).status_code == 413
        assert c.get('/healthz',headers={'host':'evil.example'}).status_code == 400

def test_real_gateway_backend_discovery(tmp_path):
    app=http_app(Config('https://lexware.example.org',digest(KEY),tmp_path),
        internal_token='test-only-internal-'+'x'*40,configured=False,manage_backend=True)
    with TestClient(app,base_url='https://lexware.example.org') as c:
        _, token=connect(c)
        headers={'Authorization':'Bearer '+token['access_token'],'Accept':'application/json, text/event-stream'}
        response=c.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
        assert response.status_code==200,response.text
        if response.headers.get('content-type','').startswith('text/event-stream'):
            data=json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
        else: data=response.json()
        names={x['name'] for x in data['result']['tools']}
        assert 'update-voucher' in names
        assert 'create-draft-invoice' not in names
