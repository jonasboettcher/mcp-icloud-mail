"""Registration survives deployment without weakening callback or secret checks."""
import asyncio
import time
from uuid import uuid4

import pytest
from mcp.shared.auth import OAuthClientInformationFull
from starlette.testclient import TestClient

from lexware_gateway.auth import CLIENT_ID_PREFIX, CLIENT_LIFETIME, digest
from lexware_gateway.server import Config, http_app
from lexware_gateway.tests.test_gateway import KEY, connect

URL = 'https://lexware.example.org'
CALLBACK = 'https://chatgpt.com/test-callback'


def authorization(client_id):
    return dict(client_id=client_id, redirect_uri=CALLBACK, response_type='code',
                code_challenge='v'*43, code_challenge_method='S256', state='bound-state',
                resource=URL+'/mcp', scope='lexware:read')


@pytest.mark.parametrize('method', ['none', 'client_secret_post'])
def test_registration_survives_empty_deployment(tmp_path, method):
    first = http_app(Config(URL, digest(KEY), tmp_path/'first'), configured=False)
    with TestClient(first, base_url=URL) as client:
        response = client.post('/register', json=dict(client_name='ChatGPT',
            redirect_uris=[CALLBACK], token_endpoint_auth_method=method,
            grant_types=['authorization_code', 'refresh_token'], response_types=['code']))
        assert response.status_code == 201, response.text
        registration = response.json()
        client_id = registration['client_id']
        assert client_id.startswith(CLIENT_ID_PREFIX)
        secret = registration.get('client_secret')
        assert not secret or secret not in client_id

    # A different empty directory models the destroyed filesystem after deploy.
    second = http_app(Config(URL, digest(KEY), tmp_path/'second'), configured=False)
    restored = asyncio.run(second.state.provider.get_client(client_id))
    assert restored.model_dump(mode='json', exclude_none=True) == registration
    with TestClient(second, base_url=URL) as client:
        response = client.get('/authorize', params=authorization(client_id), follow_redirects=False)
        assert response.status_code == 302, response.text
        assert 'Connect Lexware Office' in client.get(response.headers['location']).text
        # Recovered metadata still enforces the original callback URI.
        response = client.get('/authorize', params=dict(authorization(client_id),
            redirect_uri='https://evil.example/callback'), follow_redirects=False)
        assert response.status_code == 400
        if secret:
            response = client.post('/token', data=dict(client_id=client_id,
                client_secret='wrong-secret', grant_type='refresh_token', refresh_token='missing'))
            assert response.status_code == 401
            assert response.json()['error'] == 'unauthorized_client'
        reused_id, token = connect(client, registration=registration)
        assert reused_id == client_id
        assert token['access_token']


def test_encrypted_registration_rejects_tampering_expiry_and_wrong_key(tmp_path):
    app = http_app(Config(URL, digest(KEY), tmp_path/'first'), configured=False)
    with TestClient(app, base_url=URL) as client:
        client_id, _ = connect(client)
    provider = app.state.provider
    raw = client_id[len(CLIENT_ID_PREFIX):]
    middle = len(raw)//2
    tampered = CLIENT_ID_PREFIX + raw[:middle] + ('A' if raw[middle] != 'A' else 'B') + raw[middle+1:]
    assert asyncio.run(provider.get_client(tampered)) is None
    assert asyncio.run(provider.get_client(CLIENT_ID_PREFIX+'not-a-token')) is None
    assert asyncio.run(provider.get_client(CLIENT_ID_PREFIX+'x'*4096)) is None
    plaintext = provider.client_cipher.decrypt(raw.encode())
    expired = CLIENT_ID_PREFIX + provider.client_cipher.encrypt_at_time(
        plaintext, int(time.time())-CLIENT_LIFETIME-10).decode()
    assert asyncio.run(provider.get_client(expired)) is None
    for config in [Config(URL, digest(KEY+'changed'), tmp_path/'changed'),
                   Config('https://different.example.org', digest(KEY), tmp_path/'different')]:
        other = http_app(config, configured=False).state.provider
        assert asyncio.run(other.get_client(client_id)) is None


def test_legacy_registration_requires_existing_metadata(tmp_path):
    app = http_app(Config(URL, digest(KEY), tmp_path), configured=False)
    provider = app.state.provider
    client_id = str(uuid4())
    info = OAuthClientInformationFull(client_id=client_id, redirect_uris=[CALLBACK],
        token_endpoint_auth_method='none', grant_types=['authorization_code', 'refresh_token'],
        response_types=['code'])
    provider.store.put('client', client_id, info.model_dump(mode='json'), time.time()+3600)
    assert asyncio.run(provider.get_client(client_id)) == info
    assert asyncio.run(provider.get_client('718e02a2-1c8d-4be5-aae2-007d192d9149')) is None
