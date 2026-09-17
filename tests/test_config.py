import hashlib
import json

import pytest
from starlette.testclient import TestClient

from icloud_mail.config import load_config
from icloud_mail.server import http_app


@pytest.fixture
def environment(monkeypatch, tmp_path):
    for name in ('ICLOUD_PUBLIC_URL', 'ICLOUD_DRAFTS_FOLDER', 'ICLOUD_MAIL_CONFIG'):
        monkeypatch.delenv(name, raising=False)
    values = {
        'ICLOUD_CONFIG_SOURCE':'environment',
        'ICLOUD_EMAIL':'owner@icloud.com',
        'ICLOUD_APP_PASSWORD':'test-only-not-real',
        'ICLOUD_LOGIN_KEY':'test-key-'+'a'*40,
        'ICLOUD_STATE_DIR':str(tmp_path/'state'),
        'RENDER_EXTERNAL_URL':'https://test-service.onrender.com',
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_render_environment_health_and_auth(environment):
    config = load_config()
    assert config.public_url == environment['RENDER_EXTERNAL_URL']
    assert config.login_key_hash == hashlib.sha256(environment['ICLOUD_LOGIN_KEY'].encode()).hexdigest()
    assert environment['ICLOUD_APP_PASSWORD'] not in repr(config)
    with TestClient(http_app(config), base_url=config.public_url) as client:
        response = client.get('/healthz')
        assert response.status_code == 200 and response.json() == {'status':'ok'}
        assert 'owner@icloud.com' not in response.text
        assert client.post('/mcp', json={}).status_code == 401
        metadata = client.get('/.well-known/oauth-protected-resource/mcp').json()
        assert metadata['resource'] == environment['RENDER_EXTERNAL_URL']+'/mcp'
    assert (config.state_dir/'oauth.sqlite3').is_file()
    assert not (config.state_dir/'config.json').exists()


@pytest.mark.parametrize('missing', ['ICLOUD_EMAIL','ICLOUD_APP_PASSWORD','ICLOUD_LOGIN_KEY','ICLOUD_STATE_DIR','RENDER_EXTERNAL_URL'])
def test_missing_environment_fails_closed(environment, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError) as error:
        load_config()
    assert environment['ICLOUD_APP_PASSWORD'] not in str(error.value)


def test_environment_rejects_weak_key_and_supports_custom_origin(environment, monkeypatch):
    monkeypatch.setenv('ICLOUD_PUBLIC_URL','https://mail.example.org')
    monkeypatch.setenv('ICLOUD_DRAFTS_FOLDER','Entwürfe')
    config = load_config()
    assert config.public_url == 'https://mail.example.org'
    assert config.drafts_folder == 'Entwürfe'
    monkeypatch.setenv('ICLOUD_LOGIN_KEY','short')
    with pytest.raises(RuntimeError, match='random secret'):
        load_config()


def test_file_configuration_preserved(environment, monkeypatch, tmp_path):
    monkeypatch.setenv('ICLOUD_CONFIG_SOURCE','file')
    path = tmp_path/'config.json'
    path.write_text(json.dumps({'email':'local@icloud.com','app_password':'local-test-only'}))
    path.chmod(0o600)
    monkeypatch.setenv('ICLOUD_MAIL_CONFIG',str(path))
    assert load_config().email == 'local@icloud.com'


def test_bad_environment_does_not_expose_input(environment, monkeypatch):
    monkeypatch.setenv('ICLOUD_EMAIL', 'invalid-private-input')
    with pytest.raises(ValueError) as error:
        load_config()
    assert 'invalid-private-input' not in str(error.value)
