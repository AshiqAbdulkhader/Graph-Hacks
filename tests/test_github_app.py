import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.control import Control
from app.github_app import PERMISSIONS, app_jwt, connect_installation, consume_state, installation_token, manifest, new_state, complete_manifest


def test_app_manifest_and_state_are_scoped(tmp_path):
    ctl = Control(tmp_path)
    data = manifest(ctl, 'owner', 'http://127.0.0.1:8765')
    assert all(value == 'read' for value in data['manifest']['default_permissions'].values())
    assert 'hook_attributes' not in data['manifest']
    with pytest.raises(ValueError):
        consume_state(ctl, 'other-user', data['state'], 'app_manifest')
    consume_state(ctl, 'owner', data['state'], 'app_manifest')
    with pytest.raises(ValueError):
        consume_state(ctl, 'owner', data['state'], 'app_manifest')


def test_installation_tokens_are_short_lived_and_not_persisted(tmp_path, monkeypatch):
    ctl = Control(tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    ctl.secret_set('github_app_id', '12345')
    ctl.secret_set('github_app_private_key', pem)
    token = app_jwt(ctl)
    claims = jwt.decode(token, key.public_key(), algorithms=['RS256'])
    assert claims['iss'] == '12345'
    assert 0 < claims['exp'] - time.time() < 600
    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            return httpx.Response(200, json={'account': {'id': 99, 'login':'owner'}, 'repository_selection':'selected'},request=httpx.Request('GET',url))
        def post(self, url, **kwargs):
            assert kwargs['json']['permissions'] == PERMISSIONS
            return httpx.Response(201,json={'token':'temporary-installation-token','expires_at':'later'},request=httpx.Request('POST',url))
    monkeypatch.setattr('app.github_app.httpx.Client',MockClient)
    state = new_state(ctl,'user','app_install')
    connect_installation(ctl,'user',77,state)
    assert installation_token(ctl,'user') == 'temporary-installation-token'
    row = ctl.rows('SELECT * FROM connections')[0]
    assert row['provider'] == 'github_app'
    saved = json.loads(ctl.cipher.decrypt(row['secret'].encode()))
    assert saved['installation_id'] == 77
    assert 'token' not in saved
    assert pem not in ctl.path.read_bytes().decode(errors='ignore')


def test_manifest_without_webhooks_accepts_null_optional_secret(tmp_path, monkeypatch):
    ctl=Control(tmp_path)
    class MockClient:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            return httpx.Response(201,json={'id':123,'slug':'decisiontrail-local','pem':'private-key','webhook_secret':None},request=httpx.Request('POST',url))
    monkeypatch.setattr('app.github_app.httpx.Client',MockClient)
    state=new_state(ctl,'owner','app_manifest')
    assert complete_manifest(ctl,'owner',state,'one-time-code')=='decisiontrail-local'
    assert ctl.secret_get('github_app_private_key')=='private-key'
    assert ctl.secret_get('github_app_webhook_secret')==''
