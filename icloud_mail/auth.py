"""Single-owner OAuth provider. Protocol validation/PKCE are provided by the MCP SDK."""
import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    RefreshToken, RegistrationError, TokenError, construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.server.auth.middleware.client_auth import AuthenticationError, ClientAuthenticator
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

SCOPES = ['mail:read', 'mail:drafts']


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    """Persistent OAuth metadata; random codes/tokens are stored under SHA256 hashes."""
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        if os.name == 'posix' and path.stat().st_mode & 0o077:
            raise RuntimeError('OAuth database permissions must be 0600.')
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS items (kind TEXT, key TEXT, value TEXT, expires REAL, PRIMARY KEY(kind,key))')

    def put(self, kind, key, value, expires):
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM items WHERE expires < ?', (time.time(),))
            count = db.execute('SELECT COUNT(*) FROM items WHERE kind=?', (kind,)).fetchone()[0]
            if count >= 1024:
                raise RuntimeError('OAuth state capacity reached.')
            db.execute('INSERT OR REPLACE INTO items VALUES (?,?,?,?)', (kind, digest(key), json.dumps(value), expires))

    def get(self, kind, key, consume=False):
        with sqlite3.connect(self.path) as db:
            if consume:
                row = db.execute('DELETE FROM items WHERE kind=? AND key=? AND expires>? RETURNING value', (kind, digest(key), time.time())).fetchone()
            else:
                row = db.execute('SELECT value FROM items WHERE kind=? AND key=? AND expires>?', (kind, digest(key), time.time())).fetchone()
            return json.loads(row[0]) if row else None

    def remove_client_tokens(self, client_id):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM items WHERE kind IN ('access','refresh','code') AND json_extract(value,'$.client_id')=?", (client_id,))


class OAuthProvider:
    def __init__(self, config):
        self.config = config
        self.resource = config.public_url + '/mcp'
        if len(config.login_key_hash) != 64:
            raise RuntimeError('HTTP mode needs a login key. Run icloud-mail-setup.')
        self.store = Store(config.state_dir / 'oauth.sqlite3')

    async def get_client(self, client_id):
        value = self.store.get('client', client_id)
        return OAuthClientInformationFull.model_validate(value) if value else None

    async def register_client(self, client_info):
        if client_info.token_endpoint_auth_method not in ('none', 'client_secret_post'):
            raise RegistrationError('invalid_client_metadata', 'Supported authentication: none or client_secret_post.')
        if not client_info.redirect_uris or len(client_info.redirect_uris) > 10:
            raise RegistrationError('invalid_redirect_uri', 'One to ten redirect URIs required.')
        for uri in client_info.redirect_uris:
            u = urlsplit(str(uri))
            if u.fragment or u.username or u.password or not u.hostname or not (
                u.scheme == 'https' or (u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1', '::1'))
            ):
                raise RegistrationError('invalid_redirect_uri', 'HTTPS or loopback required.')
        self.store.put('client', client_info.client_id, client_info.model_dump(mode='json'), time.time() + 365*86400)

    async def authorize(self, client, params):
        if params.resource != self.resource:
            raise AuthorizeError('invalid_request', 'The resource must match this MCP endpoint.')
        if not set(params.scopes or []).issubset(SCOPES):
            raise AuthorizeError('invalid_scope')
        flow = secrets.token_urlsafe(32)
        self.store.put('flow', flow, {'client_id': client.client_id, 'params': params.model_dump(mode='json')}, time.time()+600)
        return self.config.public_url + '/login?flow=' + flow

    async def login(self, request):
        security = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                    'Content-Security-Policy': "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
                    'X-Content-Type-Options': 'nosniff'}
        cookie_name = '__Host-icloud-login' if self.config.public_url.startswith('https:') else 'icloud-login'
        if request.method == 'GET':
            flow = request.query_params.get('flow', '')
            record = self.store.get('flow', flow)
            if not record:
                return PlainTextResponse('Connection expired. Please reconnect.', 400, headers=security)
            csrf = secrets.token_urlsafe(32)
            self.store.put('csrf', csrf, {'flow': flow}, time.time()+600)
            client = await self.get_client(record['client_id'])
            name = html.escape((client.client_name or 'MCP client') if client else 'MCP client')
            callback = html.escape(record['params']['redirect_uri'])
            permissions = ', '.join(record['params']['scopes'] or [])
            page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Connect iCloud Mail</title>
<h1>Connect iCloud Mail</h1><p>Client: {name}</p><p>Redirect URL: {callback}</p>
<p>Permissions: {html.escape(permissions)}</p>
<p>Enter the connector key generated during setup.</p>
<form method="post" action="/login"><input type="hidden" name="flow" value="{html.escape(flow)}">
<input type="hidden" name="csrf" value="{csrf}"><label>Connector key <input type="password" name="key" required autocomplete="off"></label>
<button type="submit">Allow access</button></form></html>'''
            response = HTMLResponse(page, headers=security)
            response.set_cookie(cookie_name, csrf, httponly=True, secure=self.config.public_url.startswith('https:'), samesite='strict', max_age=600)
            return response
        form = await request.form()
        csrf, flow = str(form.get('csrf', '')), str(form.get('flow', ''))
        cookie = request.cookies.get(cookie_name, '')
        origin = request.headers.get('origin')
        if not csrf or not hmac.compare_digest(csrf, cookie) or (origin and origin != self.config.public_url):
            return PlainTextResponse('Invalid login.', 403, headers=security)
        binding = self.store.get('csrf', csrf, consume=True)
        if not binding or binding['flow'] != flow:
            return PlainTextResponse('Login expired.', 403, headers=security)
        if not hmac.compare_digest(digest(str(form.get('key', ''))), self.config.login_key_hash):
            return PlainTextResponse('Invalid key. Restart the connection.', 403, headers=security)
        record = self.store.get('flow', flow, consume=True)
        if not record:
            return PlainTextResponse('Connection expired.', 400, headers=security)
        p = AuthorizationParams.model_validate(record['params'])
        code = secrets.token_urlsafe(32)
        auth = AuthorizationCode(code=code, client_id=record['client_id'], scopes=p.scopes or [],
            expires_at=time.time()+120, code_challenge=p.code_challenge, redirect_uri=p.redirect_uri,
            redirect_uri_provided_explicitly=p.redirect_uri_provided_explicitly, resource=self.resource, subject='owner')
        self.store.put('code', code, auth.model_dump(mode='json', exclude={'code'}), auth.expires_at)
        response = RedirectResponse(construct_redirect_uri(str(p.redirect_uri), code=code, state=p.state), 303, headers=security)
        response.delete_cookie(cookie_name, secure=self.config.public_url.startswith('https:'), httponly=True, samesite='strict')
        return response

    async def load_authorization_code(self, client, authorization_code):
        value = self.store.get('code', authorization_code)
        return AuthorizationCode(code=authorization_code, **value) if value and value['client_id'] == client.client_id else None

    def issue(self, client_id, scopes):
        now = int(time.time())
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        common = dict(client_id=client_id, scopes=scopes, resource=self.resource, subject='owner')
        self.store.put('access', access, dict(common, expires_at=now+3600), now+3600)
        self.store.put('refresh', refresh, dict(common, expires_at=now+30*86400), now+30*86400)
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=3600, refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        record = self.store.get('code', authorization_code.code, consume=True)
        if not record or record['client_id'] != client.client_id:
            raise TokenError('invalid_grant')
        return self.issue(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client, refresh_token):
        value = self.store.get('refresh', refresh_token)
        return RefreshToken(token=refresh_token, **value) if value and value['client_id'] == client.client_id else None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if not set(scopes).issubset(refresh_token.scopes):
            raise TokenError('invalid_scope')
        record = self.store.get('refresh', refresh_token.token, consume=True)
        if not record or record['client_id'] != client.client_id:
            raise TokenError('invalid_grant')
        return self.issue(client.client_id, scopes)

    async def load_access_token(self, token):
        value = self.store.get('access', token)
        return AccessToken(token=token, **value) if value else None

    async def revoke_token(self, token):
        self.store.remove_client_tokens(token.client_id)

    async def revoke_request(self, request):
        # SDK 1.30 requires a client_secret form field even for registered public
        # clients. Use its authenticator, then handle RFC 7009's optional field.
        from starlette.responses import JSONResponse, Response
        headers = {'Cache-Control':'no-store', 'Pragma':'no-cache'}
        try:
            client = await ClientAuthenticator(self).authenticate_request(request)
        except AuthenticationError:
            return JSONResponse({'error':'unauthorized_client'}, 401, headers=headers)
        form = await request.form()
        raw = form.get('token')
        if not isinstance(raw, str) or not raw:
            return JSONResponse({'error':'invalid_request'}, 400, headers=headers)
        token = await self.load_access_token(raw) or await self.load_refresh_token(client, raw)
        if token and token.client_id == client.client_id:
            await self.revoke_token(token)
        return Response(status_code=200, headers=headers)
