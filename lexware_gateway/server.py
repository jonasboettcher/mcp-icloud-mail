"""OAuth gateway for the pinned Lexware MCP. No mail-account access."""
import asyncio
import os
import secrets
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes, build_metadata, cors_middleware
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from .auth import OAuthProvider, SCOPES, digest
from .guards import HTTPGuard, RequestLimits

WRITE_TOOLS = {'create-voucher', 'update-voucher', 'upload-voucher-file', 'upload-file'}

@dataclass
class Config:
    public_url: str
    login_key_hash: str
    state_dir: Path

class Verifier:
    def __init__(self, provider):
        self.provider = provider
    async def verify_token(self, token):
        return await self.provider.load_access_token(token)

def http_app(config, *, upstream='http://127.0.0.1:8081', internal_token='', configured=None, manage_backend=False):
    provider = OAuthProvider(config)
    resource = config.public_url + '/mcp'
    if configured is None:
        configured = bool(os.environ.get('LEXWARE_API_KEY', '').strip())

    @asynccontextmanager
    async def lifespan(app):
        process = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), trust_env=False) as client:
            app.state.client = client
            if manage_backend:
                env = dict(os.environ, PORT='8081', __PORT='8081', MCP_AUTH_TOKEN=internal_token,
                           LEXWARE_READ_ONLY='false', LEXWARE_ENABLE_DRAFTS='true',
                           LEXWARE_ENABLE_FINALIZE='false', LEXWARE_ENABLE_URL_UPLOAD='false',
                           SERVER_URL=config.public_url)
                # Discovery works before credentials are entered. The gateway blocks
                # every tools/call, and the backend has no route to Lexware meanwhile.
                if not configured:
                    env['LEXWARE_API_KEY'] = 'configuration-pending'
                    env['LEXWARE_API_BASE_URL'] = 'http://127.0.0.1:9'
                env.pop('OAUTH_ISSUER', None)
                process = subprocess.Popen(['node', 'dist/server.js'], cwd='.lexware-runtime', env=env)
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Lexware backend failed to start')
                    try:
                        if (await client.get(upstream + '/status')).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.1)
                else:
                    process.terminate()
                    raise RuntimeError('Lexware backend readiness timed out')
            try:
                yield
            finally:
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    async def health(request):
        return JSONResponse({'status': 'ok', 'lexware_configured': configured}, headers={'Cache-Control':'no-store'})

    async def proxy(request):
        body = await request.body()
        if request.method == 'POST':
            try:
                import json
                rpc = json.loads(body)
                if not isinstance(rpc, dict):
                    return JSONResponse({'error':'Invalid JSON-RPC request'}, 400)
            except (ValueError, UnicodeDecodeError):
                return JSONResponse({'error':'Invalid JSON'}, 400)
            if rpc.get('method') == 'tools/call':
                if not configured:
                    return JSONResponse({'jsonrpc':'2.0','id':rpc.get('id'), 'result':{
                        'isError': True, 'content':[{'type':'text','text':'LEXWARE_API_KEY is missing in Render. No Lexware request was made.'}]}})
                name = (rpc.get('params') or {}).get('name')
                if name in WRITE_TOOLS and 'lexware:vouchers' not in request.auth.scopes:
                    return JSONResponse({'error':'Missing lexware:vouchers permission'}, 403)
        headers = {key:value for key,value in request.headers.items()
                   if key.lower() in {'accept','content-type','mcp-protocol-version','mcp-session-id','last-event-id'}}
        headers['Authorization'] = 'Bearer ' + internal_token
        try:
            req = request.app.state.client.build_request(request.method, upstream+'/mcp', content=body, headers=headers)
            response = await request.app.state.client.send(req, stream=True)
        except httpx.HTTPError:
            return JSONResponse({'error':'Lexware backend unavailable'}, 503)
        passed_headers = {key:value for key,value in response.headers.items()
                          if key.lower() in {'content-type','mcp-session-id','cache-control'}}
        return StreamingResponse(response.aiter_bytes(), status_code=response.status_code,
                                 headers=passed_headers, background=BackgroundTask(response.aclose))

    protected = RequireAuthMiddleware(proxy, required_scopes=['lexware:read'],
        resource_metadata_url=AnyHttpUrl(config.public_url+'/.well-known/oauth-protected-resource/mcp'))
    # A Route treats an ASGI callable object as an ASGI app. Wrap a request endpoint.
    from starlette.routing import request_response
    protected.app = request_response(proxy)
    routes = create_auth_routes(provider, issuer_url=AnyHttpUrl(config.public_url),
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=SCOPES, default_scopes=SCOPES),
        revocation_options=RevocationOptions(enabled=True))
    routes += create_protected_resource_routes(AnyHttpUrl(resource), [AnyHttpUrl(config.public_url)], scopes_supported=SCOPES)
    metadata = build_metadata(AnyHttpUrl(config.public_url), None,
        ClientRegistrationOptions(enabled=True, valid_scopes=SCOPES, default_scopes=SCOPES), RevocationOptions(enabled=True))
    metadata.token_endpoint_auth_methods_supported = ['none', 'client_secret_post']
    metadata.revocation_endpoint_auth_methods_supported = ['none', 'client_secret_post']
    async def discovery(request):
        return JSONResponse(metadata.model_dump(mode='json', exclude_none=True))
    for i, route in enumerate(routes):
        if route.path == '/revoke':
            routes[i] = Route('/revoke', cors_middleware(provider.revoke_request, ['POST','OPTIONS']), methods=['POST','OPTIONS'])
        if route.path == '/.well-known/oauth-authorization-server':
            routes[i] = Route(route.path, cors_middleware(discovery, ['GET','OPTIONS']), methods=['GET','OPTIONS'])
    routes += [Route('/login', provider.login, methods=['GET','POST']), Route('/healthz', health),
               Route('/mcp', protected, methods=['GET','POST','DELETE'])]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(AuthenticationMiddleware, backend=BearerAuthBackend(Verifier(provider), resource_server_url=AnyHttpUrl(resource)))
    app.add_middleware(HTTPGuard, resource=resource)
    app.add_middleware(RequestLimits)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(config.public_url).hostname])
    app.state.provider = provider
    return app

def main():
    public_url = (os.environ.get('LEXWARE_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL','')).rstrip('/')
    key = os.environ.get('LEXWARE_LOGIN_KEY','')
    if not public_url.startswith('https://') or len(key) < 32:
        raise RuntimeError('HTTPS public URL and LEXWARE_LOGIN_KEY (32+ characters) are required')
    config = Config(public_url, digest(key), Path(os.environ.get('LEXWARE_STATE_DIR', '/tmp/lexware-oauth')))
    app = http_app(config, internal_token=secrets.token_urlsafe(48), manage_backend=True)
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT','10000')), access_log=False, log_level='warning')

if __name__ == '__main__':
    main()
