"""Cloudflare entrypoint. Bound request bodies before the ASGI adapter buffers them."""

from app import app
from middleware import MAX_BODY_BYTES, payload_too_large_response, response_headers
from workers import Request, Response, asgi


class Default(asgi.entrypoint(app)):
    async def fetch(self, request):
        if not isinstance(request, Request):
            request = Request(request)
        if request.body:
            body = bytearray()
            async for chunk in request.body:
                if len(body) + chunk.byteLength > MAX_BODY_BYTES:
                    response = payload_too_large_response()
                    headers = dict(response.headers)
                    headers.update(response_headers(
                        request.headers.get("origin"), self.env, request.url.startswith("https:")))
                    return Response(response.body, status=413, headers=headers)
                body.extend(chunk.to_bytes())
            request = Request(request, body=bytes(body))
        return await super().fetch(request)
