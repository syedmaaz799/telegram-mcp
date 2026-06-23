import pytest

from telegram_mcp import runner
from telegram_mcp.runtime import ServerCliConfig


class _FakeClient:
    def __init__(self, *, authorized: bool):
        self.authorized = authorized
        self.connected = False
        self.started = False

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return self.authorized

    async def start(self):
        self.started = True


@pytest.mark.asyncio
async def test_connect_authorized_client_uses_existing_session_without_interactive_start():
    client = _FakeClient(authorized=True)

    await runner._connect_authorized_client("default", client)

    assert client.connected is True
    assert client.started is False


@pytest.mark.asyncio
async def test_connect_authorized_client_rejects_unauthorized_session():
    client = _FakeClient(authorized=False)

    with pytest.raises(RuntimeError, match="Interactive phone login is disabled"):
        await runner._connect_authorized_client("default", client)

    assert client.connected is True
    assert client.started is False


@pytest.mark.asyncio
async def test_run_mcp_server_uses_stdio_transport(monkeypatch):
    calls = []

    async def fake_stdio():
        calls.append("stdio")

    monkeypatch.setattr(runner.mcp, "run_stdio_async", fake_stdio)
    monkeypatch.setattr(runner, "_serve_streamable_http", lambda host, port: calls.append("http"))

    config = ServerCliConfig(
        transport="stdio",
        host="0.0.0.0",
        port=8000,
        allowed_roots=(),
    )
    await runner._run_mcp_server(config)

    assert calls == ["stdio"]


@pytest.mark.asyncio
async def test_run_mcp_server_uses_streamable_http_transport(monkeypatch):
    calls = []

    async def fake_http(host, port):
        calls.append(("http", host, port))

    monkeypatch.setattr(runner.mcp, "run_stdio_async", lambda: calls.append("stdio"))
    monkeypatch.setattr(runner, "_serve_streamable_http", fake_http)
    monkeypatch.setattr(runner, "_apply_mcp_http_settings", lambda host, port: calls.append((host, port)))

    config = ServerCliConfig(
        transport="streamable-http",
        host="0.0.0.0",
        port=8123,
        allowed_roots=(),
    )
    await runner._run_mcp_server(config)

    assert calls[0] == ("0.0.0.0", 8123)
    assert calls[1] == ("http", "0.0.0.0", 8123)
