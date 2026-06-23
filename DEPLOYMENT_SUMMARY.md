# Telegram MCP — Deployment Work Summary

This document summarizes the analysis and implementation work done to prepare **telegram-mcp** for **Railway** deployment and **Dify Cloud** MCP connections. It also records known issues that were not fully resolved in the local development environment.

---

## 1. Starting point (analysis)

An initial compatibility review found:

| Area | Finding |
|------|---------|
| MCP framework | **FastMCP** (from the official Python `mcp` SDK) |
| Original transport | **stdio only** — suitable for Claude Desktop / Cursor, not remote cloud clients |
| Public HTTP endpoint | **None** — not connectable by Dify Cloud as-is |
| Telegram auth | Pre-authorized **session string** or **file session** via env vars; no interactive login in the server |
| Deployment readiness | **Major changes needed** |

Dify Cloud expects a remotely reachable **Streamable HTTP** MCP endpoint (URL ending in `/mcp`). Railway expects a process that binds to `0.0.0.0` and listens on the `PORT` environment variable.

---

## 2. What was implemented

### 2.1 Dual transport support

The server now supports two MCP transports:

- **`stdio`** (default) — unchanged behavior for local MCP clients
- **`streamable-http`** — for Railway and Dify Cloud

Transport is selected via CLI:

```bash
telegram-mcp --transport stdio
telegram-mcp --transport streamable-http --host 0.0.0.0 --port $PORT
```

### 2.2 CLI arguments

Added to `telegram_mcp/runtime.py`:

| Argument | Default |
|----------|---------|
| `--transport` | `stdio` |
| `--host` | `0.0.0.0` |
| `--port` | `int(os.getenv("PORT", "8000"))` |

Positional **allowed roots** for file-path tools still work as before.

### 2.3 FastMCP HTTP configuration

`FastMCP` is initialized with Railway-friendly defaults:

```python
FastMCP("telegram", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
```

Before starting streamable HTTP, `mcp.settings.host` and `mcp.settings.port` are updated from CLI values, then:

```python
await mcp.run_streamable_http_async()
```

Uses the installed **mcp 1.22.0** API (`run_stdio_async` / `run_streamable_http_async`).

### 2.4 Railway deployment files

| File | Purpose |
|------|---------|
| `Procfile` | `web: telegram-mcp --transport streamable-http --host 0.0.0.0 --port $PORT` |
| `railway.json` | Docker build + Railway start command |
| `Dockerfile` | `pip install .`, `EXPOSE 8000`, default CMD still `python main.py` (stdio) for local Docker |

### 2.5 Documentation

`README.md` was extended with a **Railway Deployment** section covering:

- Session string generation (must be done locally)
- Required Railway environment variables
- Dify Cloud MCP URL format
- Local streamable-http testing

### 2.6 Tests added

New unit tests in:

- `tests/test_runtime.py` — CLI parsing and HTTP settings
- `tests/test_runner.py` — transport routing (`stdio` vs `streamable-http`)

### 2.7 Intentionally not changed

Per requirements:

- No Telegram tool modules modified
- No authentication logic modified (session env vars, `session_string_generator.py`, `_connect_authorized_client` behavior unchanged)

---

## 3. Files changed

| File | Change |
|------|--------|
| `telegram_mcp/runtime.py` | `ServerCliConfig`, CLI args, FastMCP host/port defaults, `_apply_mcp_http_settings()` |
| `telegram_mcp/runner.py` | `_run_mcp_server()`, transport selection in `_main()` |
| `tests/test_runtime.py` | CLI and settings tests |
| `tests/test_runner.py` | Transport routing tests |
| `Dockerfile` | Install package via `pip install .`, expose port 8000 |
| `Procfile` | **New** |
| `railway.json` | **New** |
| `README.md` | Railway + Dify documentation |

---

## 4. How to use after deployment

### Railway startup command

```bash
telegram-mcp --transport streamable-http --host 0.0.0.0 --port $PORT
```

### Dify Cloud MCP URL

```text
https://<your-railway-domain>/mcp
```

The path must end with `/mcp` (FastMCP default `streamable_http_path`).

### Required Railway environment variables

| Variable | Required |
|----------|----------|
| `TELEGRAM_API_ID` | Yes |
| `TELEGRAM_API_HASH` | Yes |
| `TELEGRAM_SESSION_STRING` | Yes (recommended over file sessions) |
| `PORT` | Set automatically by Railway |

Generate the session string locally:

```bash
uv run session_string_generator.py --qr
# or
uv run session_string_generator.py --phone
```

### Local stdio (unchanged)

```bash
uv run main.py
```

---

## 5. Errors fixed in this pass

### 5.1 Pytest `INTERNALERROR` — install guard + duplicate metadata

**Status:** Fixed in `telegram_mcp/install_guard.py`.

`assert_safe_distribution()` now enumerates **all** installed `telegram-mcp` distribution records via `metadata.distributions()` and accepts the install when **any** record has a trusted source checkout or valid `direct_url.json`.

Unit tests cover single valid, duplicate (one invalid + one valid), and all-invalid cases.

**Note:** On Windows, prefer `uv run python -m pytest` if `uv run pytest` fails due to a stale pytest entrypoint shim.

### 5.2 Public MCP endpoint without authentication

**Status:** Fixed in `telegram_mcp/http_auth.py`.

When `MCP_API_KEY` is set, streamable HTTP requests to `/mcp` require `Authorization: Bearer <MCP_API_KEY>`:

- **401** — missing `Authorization` header
- **403** — invalid scheme or token

`GET /health` is unauthenticated for Railway health checks. Stdio transport is unaffected.

---

## 6. Remaining deployment blockers (operational)

These are operational constraints, not unfinished implementation in this repo:

| Blocker | Reason |
|---------|--------|
| Session must be created before deploy | MCP server disables interactive phone/QR login; use `session_string_generator.py` locally |
| Dify Cloud may return 403 | Dify routes outbound MCP traffic through an SSRF proxy that may block external Railway domains until allowlisted |
| No HTTP auth on MCP endpoint | **Fixed** — `MCP_API_KEY` + Bearer auth on `/mcp` |
| File-path tools on Railway | Need allowed roots or volumes; ephemeral disk limits upload/download workflows |
| Unrelated PyPI package name | Do not `pip install telegram-mcp` from PyPI — use this repo or `git+https://github.com/chigwell/telegram-mcp.git` |

---

## 7. Status overview

| Item | Status |
|------|--------|
| stdio transport (local MCP clients) | Done — default, unchanged |
| streamable-http transport (Railway / Dify) | Done |
| CLI `--transport`, `--host`, `--port` | Done |
| Railway `Procfile` + `railway.json` | Done |
| Dockerfile HTTP port exposure | Done |
| README deployment docs | Done |
| Full local `pytest` on Windows | **Verified** — 130 passed via `uv run python -m pytest` |
| Dify Cloud end-to-end connection | **Not tested** — requires deployed Railway URL + Dify workspace access |

---

## 8. Recommended next steps

1. **Fix install guard** to handle duplicate distribution metadata (enables reliable local `pytest`).
2. **Deploy to Railway** with `TELEGRAM_SESSION_STRING` and confirm `https://<domain>/mcp` responds.
3. **Connect Dify Cloud** using the `/mcp` URL; escalate 403 errors to Dify if SSRF proxy blocks the domain.
4. **Add HTTP authentication** before exposing production Telegram access on a public URL.
5. **Run CI** (`uv run pytest`) on GitHub Actions to confirm tests pass in a clean Linux environment.

---

*Generated as a session summary for the Railway + Dify Cloud deployment work on telegram-mcp.*
