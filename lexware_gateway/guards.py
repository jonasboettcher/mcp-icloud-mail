import time
from collections import defaultdict, deque
from urllib.parse import parse_qs
from mcp.server.transport_security import RequestBodyLimitMiddleware
from starlette.responses import JSONResponse, PlainTextResponse

class RequestLimits:
    """Allow Base64 file uploads only on MCP; keep authentication requests small."""
    def __init__(self, app):
        self.mcp = RequestBodyLimitMiddleware(app, max_body_size=16*1024*1024)
        self.auth = RequestBodyLimitMiddleware(app, max_body_size=1024*1024)

    async def __call__(self, scope, receive, send):
        limited = self.mcp if scope.get('path') == '/mcp' else self.auth
        await limited(scope, receive, send)


class HTTPGuard:
    """Global auth endpoint rate limits for one owner; never trusts proxy client-IP headers."""
    def __init__(self, app, resource):
        self.app, self.resource = app, resource
        self.hits = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope['path']
            limits = {'/register': 10, '/authorize': 30, '/login': 30, '/token': 60}
            if path in limits:
                now, hits = time.monotonic(), self.hits[path]
                while hits and hits[0] < now-60:
                    hits.popleft()
                if len(hits) >= limits[path]:
                    return await PlainTextResponse('Too many requests', 429, headers={'Retry-After':'60'})(scope, receive, send)
                hits.append(now)
            if path == '/token' and scope['method'] == 'POST':
                # SDK validates PKCE; bind any resource supplied at token exchange too.
                messages, body = [], b''
                while True:
                    message = await receive()
                    messages.append(message)
                    if message['type'] == 'http.disconnect':
                        return
                    body += message.get('body', b'')
                    if not message.get('more_body'):
                        break
                form = parse_qs(body.decode('utf-8', errors='replace'))
                if 'resource' in form and form['resource'] != [self.resource]:
                    return await JSONResponse({'error': 'invalid_target'}, 400)(scope, receive, send)
                queue = deque(messages)
                original_receive = receive
                async def replay():
                    return queue.popleft() if queue else await original_receive()
                receive = replay
        await self.app(scope, receive, send)

