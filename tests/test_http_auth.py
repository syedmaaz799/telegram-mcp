import json

import pytest
from starlette.responses import JSONResponse

from telegram_mcp.http_auth import ApiKeyAuthMiddleware


class _CaptureApp:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        response = JSONResponse({"ok": True})
        await response(scope, receive, send)


def _http_scope(*, path: str = "/mcp", authorization: str | None = None) -> dict:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    return {"type": "http", "path": path, "headers": headers}


async def _collect_response(middleware, scope):
    app = _CaptureApp()
    wrapped = ApiKeyAuthMiddleware(app, "secret-key")
    messages = []

    async def send(message):
        messages.append(message)

    await wrapped(scope, None, send)
    return app.called, messages


@pytest.mark.asyncio
async def test_api_key_auth_allows_health_without_authorization():
    called, messages = await _collect_response(ApiKeyAuthMiddleware(_CaptureApp(), "secret-key"), _http_scope(path="/health"))
    assert called is True
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_api_key_auth_returns_401_when_authorization_missing():
    called, messages = await _collect_response(ApiKeyAuthMiddleware(_CaptureApp(), "secret-key"), _http_scope())
    assert called is False
    assert messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_api_key_auth_returns_403_for_invalid_token():
    called, messages = await _collect_response(
        ApiKeyAuthMiddleware(_CaptureApp(), "secret-key"),
        _http_scope(authorization="Bearer wrong"),
    )
    assert called is False
    assert messages[0]["status"] == 403


@pytest.mark.asyncio
async def test_api_key_auth_allows_valid_bearer_token():
    called, messages = await _collect_response(
        ApiKeyAuthMiddleware(_CaptureApp(), "secret-key"),
        _http_scope(authorization="Bearer secret-key"),
    )
    assert called is True
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_api_key_auth_returns_403_for_non_bearer_scheme():
    called, messages = await _collect_response(
        ApiKeyAuthMiddleware(_CaptureApp(), "secret-key"),
        _http_scope(authorization="Basic secret-key"),
    )
    assert called is False
    assert messages[0]["status"] == 403
