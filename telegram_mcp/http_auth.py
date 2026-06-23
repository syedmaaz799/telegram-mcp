"""HTTP authentication helpers for the streamable MCP transport."""

from __future__ import annotations

import json
import secrets
from typing import Any

from starlette.types import Receive, Scope, Send


class ApiKeyAuthMiddleware:
    """Require ``Authorization: Bearer <MCP_API_KEY>`` for HTTP MCP requests."""

    def __init__(self, app: Any, api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/health":
            await self.app(scope, receive, send)
            return

        auth_header = _get_authorization_header(scope)
        if auth_header is None:
            await _send_auth_error(send, status_code=401, error="unauthorized", description="Missing Authorization header")
            return

        if not auth_header.lower().startswith("bearer "):
            await _send_auth_error(
                send,
                status_code=403,
                error="forbidden",
                description="Authorization header must use Bearer scheme",
            )
            return

        token = auth_header[7:].strip()
        if not token or not secrets.compare_digest(token, self.api_key):
            await _send_auth_error(send, status_code=403, error="forbidden", description="Invalid bearer token")
            return

        await self.app(scope, receive, send)


def _get_authorization_header(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"authorization":
            return value.decode("latin-1")
    return None


async def _send_auth_error(send: Send, *, status_code: int, error: str, description: str) -> None:
    body_bytes = json.dumps({"error": error, "error_description": description}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body_bytes)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body_bytes})
