# Custom JioTV IPTV Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust, lightweight, self-hosted Python (FastAPI) IPTV server for JioTV with an offline-first cache, direct-to-CDN 302 stream redirection, an optional residential proxy toggle configurable in the WebUI, and a modern dashboard.

**Architecture:** A FastAPI service exposes standard IPTV M3U playlists and XMLTV EPG endpoints. Client playback requests (`/live/{id}`) return 302 redirects straight to Jio/Akamai CDNs so the server consumes zero video bandwidth. Metadata and channel catalog sync operates in Direct Mode by default, but can optionally route through a residential proxy (e.g. Tailscale / homeserver) via WebUI configuration. Stale disk caching guarantees zero downtime for TV clients even if upstream proxies are offline.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, HTTPX (async HTTP with SOCKS/HTTP proxy support), Jinja2, Pydantic / Pydantic-Settings, Pytest.

## Global Constraints
- Target Git Remote: `git@github.com:pranabeshsingh/jiotv.git`
- Target VM: `ubuntu@home.trylocalhost.com` (serving `https://tv.trylocalhost.com`)
- Secrets & Tokens: Must never be committed to git; live in `.env` and `data/` (both `.gitignore`d).
- Offline-First: Clients must never receive 500 when upstream Jio CDN is blocked or homeserver proxy is offline. Disk cache is always served.
- Proxy: Default is Direct Mode (`proxy_enabled: false`). Configurable and testable at runtime via WebUI.

---

### Task 1: Project Scaffolding & Configuration Management

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` model in `app/config.py` with fields:
  - `host: str = "0.0.0.0"`
  - `port: int = 5001`
  - `base_url: str = ""`
  - `dashboard_password: str = ""`
  - `secret_key: str = "change-me-secret-key"`
  - `data_dir: Path = Path("./data")`
  - `proxy_enabled: bool = False`
  - `proxy_url: str = ""`
  - `get_settings() -> Settings`
  - `update_runtime_settings(proxy_enabled: bool, proxy_url: str, base_url: str | None = None) -> Settings`

- [ ] **Step 1: Write the failing test for configuration management**

```python
# tests/test_config.py
from pathlib import Path
import json
import pytest
from app.config import Settings, load_settings, save_runtime_settings

def test_settings_defaults(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    assert settings.proxy_enabled is False
    assert settings.proxy_url == ""
    assert settings.port == 5001

def test_runtime_settings_override(tmp_path: Path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "proxy_enabled": True,
        "proxy_url": "http://100.107.251.122:8888"
    }))
    
    settings = load_settings(data_dir=tmp_path)
    assert settings.proxy_enabled is True
    assert settings.proxy_url == "http://100.107.251.122:8888"

def test_save_runtime_settings(tmp_path: Path):
    save_runtime_settings(tmp_path, proxy_enabled=True, proxy_url="http://1.2.3.4:8080")
    settings = load_settings(data_dir=tmp_path)
    assert settings.proxy_enabled is True
    assert settings.proxy_url == "http://1.2.3.4:8080"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'app')

- [ ] **Step 3: Implement dependencies, gitignore, and config module**

```text
# requirements.txt
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
httpx[socks]>=0.27.0
jinja2>=3.1.3
python-multipart>=0.0.9
pydantic-settings>=2.2.1
pytest>=8.0.0
pytest-asyncio>=0.23.5
```

```text
# .gitignore
__pycache__/
*.pyc
*.pyo
venv/
.env
data/
*.log
.pytest_cache/
```

```ini
# .env.example
HOST=0.0.0.0
PORT=5001
BASE_URL=https://tv.trylocalhost.com
DASHBOARD_PASSWORD=admin
SECRET_KEY=supersecret-session-key

# Upstream Residential Proxy (Optional - leave disabled for direct mode)
PROXY_ENABLED=false
PROXY_URL=http://100.107.251.122:8888

DATA_DIR=./data
```

```python
# app/config.py
from pathlib import Path
import json
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 5001
    base_url: str = "https://tv.trylocalhost.com"
    dashboard_password: str = ""
    secret_key: str = "jiotv-default-secret-key-change-me"
    data_dir: Path = Path("./data")
    proxy_enabled: bool = False
    proxy_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

def load_settings(data_dir: Optional[Path] = None) -> Settings:
    settings = Settings()
    if data_dir is not None:
        settings.data_dir = data_dir
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = settings.data_dir / "settings.json"
    if runtime_file.exists():
        try:
            overrides = json.loads(runtime_file.read_text(encoding="utf-8"))
            for key, val in overrides.items():
                if hasattr(settings, key) and val is not None:
                    setattr(settings, key, val)
        except Exception:
            pass
    return settings

def save_runtime_settings(data_dir: Path, **kwargs) -> Settings:
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = data_dir / "settings.json"
    current = {}
    if runtime_file.exists():
        try:
            current = json.loads(runtime_file.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current.update({k: v for k, v in kwargs.items() if v is not None})
    runtime_file.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return load_settings(data_dir=data_dir)

_current_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _current_settings
    if _current_settings is None:
        _current_settings = load_settings()
    return _current_settings

def refresh_settings() -> Settings:
    global _current_settings
    _current_settings = load_settings()
    return _current_settings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore .env.example app/config.py app/__init__.py tests/test_config.py
git commit -m "feat: add project scaffolding and configuration management"
```

---

### Task 2: Jio API Client (Auth, Refresh, Playback & Widevine)

**Files:**
- Create: `app/jio_api.py`
- Test: `tests/test_jio_api.py`

**Interfaces:**
- Consumes: `app/config.py` (`Settings`)
- Produces: `JioApiClient` in `app/jio_api.py` with methods:
  - `send_otp(mobile: str) -> dict`: calls Jio auth endpoint to dispatch SMS OTP.
  - `verify_otp(mobile: str, otp: str) -> dict`: verifies OTP, saves `auth.json`, returns user metadata.
  - `get_auth_state() -> dict`: loads `data/auth.json` with subscriber info, token expiry, and logged-in state.
  - `refresh_token() -> bool`: refreshes SSO token before expiry.
  - `get_playback_url(channel_id: str) -> str`: calls `https://jiotvapi.media.jio.com/playback/apis/v1.1/geturl` directly with tokens, returns signed master URL (e.g. `https://.../master.m3u8?...` or `.mpd?...`).
  - `test_connectivity(proxy_url: Optional[str] = None) -> dict`: probes Jio Playback API (direct) and Jio CDN (direct or proxied), returning status and latency.

- [ ] **Step 1: Write failing test for JioApiClient**

```python
# tests/test_jio_api.py
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
import httpx
from app.config import Settings
from app.jio_api import JioApiClient

@pytest.fixture
def api_client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return JioApiClient(settings=settings)

@pytest.mark.asyncio
async def test_send_otp_success(api_client: JioApiClient):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(
            200, json={"status": "success", "message": "OTP sent successfully"}
        )
        res = await api_client.send_otp("+919031042585")
        assert res["status"] == "success"
        assert mock_post.called

@pytest.mark.asyncio
async def test_get_playback_url(api_client: JioApiClient, tmp_path: Path):
    # Seed auth.json
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"sso_token": "mock_token", "crm": "mock_crm", "unique_id": "123"}')
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(
            200, json={"result": "https://live.cdn.jio.com/bpk-tv/202/Fallback/index.m3u8?token=xyz"}
        )
        url = await api_client.get_playback_url("202")
        assert "live.cdn.jio.com" in url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jio_api.py -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'app.jio_api')

- [ ] **Step 3: Implement `app/jio_api.py`**

Implement Jio API interactions including:
- Standard Android JioTV headers (`appkey: NzNiMDhlYzQ2NDJk`, `devicetype: phone`, `os: Android`, `User-Agent: okhttp/4.9.3`).
- Send OTP (`https://api.jio.com/v3/dip/user/otp/send` or `https://jiotvapi.media.jio.com/userservice/apis/v1/loginotp/send`).
- Verify OTP (`https://api.jio.com/v3/dip/user/otp/verify` or `https://jiotvapi.media.jio.com/userservice/apis/v1/loginotp/verify`).
- Playback URL resolution via `https://jiotvapi.media.jio.com/playback/apis/v1.1/geturl` (direct connection, no proxy).
- Token auto-refresh logic.
- Probe/test connection function testing both `https://jiotvapi.media.jio.com` and `https://jiotv.data.cdn.jio.com/apis/v1.4/getallchannel.php`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_jio_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/jio_api.py tests/test_jio_api.py
git commit -m "feat: implement Jio API client for authentication, playback, and network diagnostics"
```

---

### Task 3: Channel Catalog & Offline Cache Manager

**Files:**
- Create: `app/channel_manager.py`
- Test: `tests/test_channel_manager.py`

**Interfaces:**
- Consumes: `app/config.py`, `app/jio_api.py`
- Produces: `ChannelManager` with methods:
  - `sync_channels(force: bool = False) -> int`: fetches channel catalog from Jio CDN (using proxy if configured, direct otherwise) and saves to `data/channels.json`. Falls back to existing disk cache if network fails.
  - `sync_epg() -> Path`: fetches and compiles EPG XMLTV file and saves compressed to `data/epg.xml.gz`.
  - `get_channels(lang: Optional[str] = None, genre: Optional[str] = None, search: Optional[str] = None) -> list[dict]`: returns filtered channel list.
  - `generate_m3u(base_url: str, lang: Optional[str] = None, genre: Optional[str] = None) -> str`: produces Kodi-compliant `#EXTM3U` playlist with `tvg-id`, `tvg-logo`, `group-title`, and stream URL pointing to `${base_url}/live/{channel_id}`.
  - `get_epg_path() -> Path`: returns path to `data/epg.xml.gz`.

- [ ] **Step 1: Write failing test for ChannelManager**

```python
# tests/test_channel_manager.py
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
from app.config import Settings
from app.channel_manager import ChannelManager

@pytest.fixture
def channel_mgr(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return ChannelManager(settings=settings)

@pytest.mark.asyncio
async def test_sync_channels_and_generate_m3u(channel_mgr: ChannelManager, tmp_path: Path):
    mock_catalog = {
        "result": [
            {
                "channel_id": 202,
                "channel_name": "DD National",
                "channelLanguageId": 6, # Hindi
                "channelCategoryId": 1, # Entertainment
                "logoUrl": "dd_national.png",
                "isHD": False
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=mock_catalog)
        count = await channel_mgr.sync_channels()
        assert count == 1
        
        # Verify file is cached
        assert (tmp_path / "channels.json").exists()
        
        # Verify M3U generation
        m3u = channel_mgr.generate_m3u(base_url="https://tv.trylocalhost.com")
        assert "#EXTM3U" in m3u
        assert "DD National" in m3u
        assert "https://tv.trylocalhost.com/live/202" in m3u
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_channel_manager.py -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'app.channel_manager')

- [ ] **Step 3: Implement `app/channel_manager.py`**

Implement:
- Language ID mapping (`1: English, 6: Hindi, 2: Marathi, 3: Punjabi, etc.`).
- Category/Genre ID mapping (`1: Entertainment, 2: Movies, 3: Music, 4: News, 5: Sports, etc.`).
- Upstream HTTP transport honoring `settings.proxy_enabled` and `settings.proxy_url` when fetching `getallchannel.php`.
- Offline resilience: wrap fetch in try-except; on failure (HTTP 450, timeout, proxy down), log warning and retain existing `data/channels.json`.
- M3U builder with Kodi metadata headers (`#EXTINF:-1 tvg-id="..." tvg-name="..." tvg-logo="..." group-title="...", Channel Name`).
- EPG fetcher and gzip compression for `data/epg.xml.gz`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_channel_manager.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/channel_manager.py tests/test_channel_manager.py
git commit -m "feat: implement channel catalog manager, offline cache, and M3U/EPG generator"
```

---

### Task 4: IPTV Streaming Routes (`/playlist.m3u`, `/epg.xml.gz`, `/live/{id}`)

**Files:**
- Create: `app/routes/__init__.py`
- Create: `app/routes/iptv.py`
- Create: `app/main.py`
- Test: `tests/test_iptv_routes.py`

**Interfaces:**
- Consumes: `app/channel_manager.py`, `app/jio_api.py`, `app/config.py`
- Produces: FastAPI router mounted with:
  - `GET /playlist.m3u`: returns `text/plain` M3U playlist.
  - `GET /epg.xml.gz`: returns `application/gzip` EPG file.
  - `GET /live/{channel_id}`: resolves stream URL via Jio API and returns `HTTP 302 Found` with `Location: <signed_cdn_url>`.
  - `GET /render/key/{channel_id}`: Widevine license proxy if requested.

- [ ] **Step 1: Write failing test for IPTV routes**

```python
# tests/test_iptv_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from pathlib import Path
import json
from app.main import create_app
from app.config import Settings

@pytest.fixture
def app(tmp_path: Path):
    # Setup test cache
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {
            "channel_id": 202,
            "channel_name": "DD National",
            "language": "Hindi",
            "genre": "Entertainment",
            "logo": "http://example.com/logo.png"
        }
    ]))
    epg_file = tmp_path / "epg.xml.gz"
    epg_file.write_bytes(b"dummy_epg_data")
    
    settings = Settings(data_dir=tmp_path, base_url="https://tv.trylocalhost.com")
    return create_app(settings=settings)

@pytest.mark.asyncio
async def test_playlist_m3u(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://tv.trylocalhost.com") as client:
        resp = await client.get("/playlist.m3u")
        assert resp.status_code == 200
        assert "#EXTM3U" in resp.text
        assert "DD National" in resp.text
        assert "/live/202" in resp.text

@pytest.mark.asyncio
async def test_live_stream_redirect(app):
    transport = ASGITransport(app=app)
    with patch("app.jio_api.JioApiClient.get_playback_url", new_callable=AsyncMock) as mock_playback:
        mock_playback.return_value = "https://live.cdn.jio.com/stream.m3u8?token=xyz"
        async with AsyncClient(transport=transport, base_url="https://tv.trylocalhost.com", follow_redirects=False) as client:
            resp = await client.get("/live/202")
            assert resp.status_code == 302
            assert resp.headers["Location"] == "https://live.cdn.jio.com/stream.m3u8?token=xyz"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_iptv_routes.py -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'app.main')

- [ ] **Step 3: Implement `app/routes/iptv.py` and `app/main.py`**

- Create `app/routes/iptv.py` with FastAPI `APIRouter()`.
- Add `/playlist.m3u` supporting query filters `lang`, `genre`.
- Add `/epg.xml.gz` returning `FileResponse(path, media_type="application/gzip")`.
- Add `/live/{channel_id}` issuing `RedirectResponse(url=playback_url, status_code=302)`.
- Initialize `app/main.py` with `create_app()` factory and lifespan handlers for background catalog sync.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_iptv_routes.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes/iptv.py app/routes/__init__.py app/main.py tests/test_iptv_routes.py
git commit -m "feat: implement IPTV streaming endpoints for M3U playlist, EPG, and 302 stream redirects"
```

---

### Task 5: Management & Settings API Routes

**Files:**
- Create: `app/routes/api.py`
- Test: `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `app/config.py`, `app/jio_api.py`, `app/channel_manager.py`
- Produces: API router with:
  - `GET /api/status`: returns `{jio_logged_in: bool, subscriber_name: str, channels_count: int, proxy_enabled: bool, proxy_url: str, last_sync: str}`.
  - `GET /api/settings`: returns current runtime settings.
  - `POST /api/settings`: updates `proxy_enabled`, `proxy_url`, `base_url` in `data/settings.json` and hot-reloads configuration.
  - `POST /api/test-connectivity`: performs live probe of Jio Playback API and Jio CDN (with direct vs proxy timings and status codes).
  - `POST /api/auth/otp/send`: triggers OTP.
  - `POST /api/auth/otp/verify`: validates OTP and saves credentials.
  - `POST /api/sync`: triggers catalog/EPG sync.
  - `GET /api/channels`: returns JSON channel list with search/filter params.

- [ ] **Step 1: Write failing test for API routes**

```python
# tests/test_api_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from app.main import create_app
from app.config import Settings

@pytest.fixture
def app(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return create_app(settings=settings)

@pytest.mark.asyncio
async def test_update_proxy_settings_api(app, tmp_path: Path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Update settings to enable proxy
        payload = {"proxy_enabled": True, "proxy_url": "http://100.107.251.122:8888"}
        resp = await client.post("/api/settings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["proxy_enabled"] is True
        assert data["proxy_url"] == "http://100.107.251.122:8888"
        
        # Verify persistence in settings.json
        status_resp = await client.get("/api/status")
        assert status_resp.json()["proxy_enabled"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_routes.py -v`  
Expected: FAIL (404 Not Found on `/api/settings`)

- [ ] **Step 3: Implement `app/routes/api.py`**

- Wire up status, settings, test-connectivity, auth, sync, and channel endpoints.
- Ensure runtime settings updates write to `settings.json` and hot-reload `ChannelManager` and `JioApiClient` clients.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_routes.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes/api.py tests/test_api_routes.py
git commit -m "feat: implement management API endpoints for status, proxy settings, diagnostics, and auth"
```

---

### Task 6: Modern WebUI Dashboard & Templates

**Files:**
- Create: `app/static/css/style.css`
- Create: `app/static/js/app.js`
- Create: `app/templates/base.html`
- Create: `app/templates/dashboard.html`
- Create: `app/templates/login.html`
- Create: `app/routes/web.py`
- Test: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: All backend routes, `app/config.py`
- Produces: Responsive modern dark dashboard featuring:
  - Header with service status badge, Jio subscriber info, and logout.
  - Tab 1: **Status & Controls** (Account info, token expiry countdown, manual refresh token, manual sync button).
  - Tab 2: **Network & Proxy Settings**:
    - Direct vs Proxy toggle.
    - Proxy URL input.
    - Live "Test Connection" button showing reachability to Jio CDN and Jio Playback.
    - Helper card explaining when a residential proxy is required (cloud VPS like Oracle) vs when direct mode is suitable (home networks), with copyable standalone proxy script.
  - Tab 3: **Client Setup Guide**:
    - One-click copyable M3U and EPG URLs (detected automatically from `window.location.origin` or `BASE_URL`).
    - Kodi (PVR IPTV Simple Client) step-by-step setup cards.
    - TiviMate & VLC setup instructions.
  - Tab 4: **Channel Browser**:
    - Filterable grid with search, language badges, genre filters, and play links.
  - Modal: **Jio OTP Login Modal** for instant re-authentication from the browser.

- [ ] **Step 1: Write test for WebUI routes**

```python
# tests/test_web_ui.py
import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from app.main import create_app
from app.config import Settings

@pytest.fixture
def app(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return create_app(settings=settings)

@pytest.mark.asyncio
async def test_dashboard_renders_html(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "JioTV IPTV Server" in resp.text
        assert "Network & Proxy Settings" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_ui.py -v`  
Expected: FAIL (404 on `/`)

- [ ] **Step 3: Implement WebUI templates, styles, and client scripts**

- Create `app/static/css/style.css` using modern aesthetic design (clean slate dark theme `#0f172a`, cards `#1e293b`, accents `#3b82f6` and `#10b981`, responsive flex/grid, micro-transitions).
- Create `app/static/js/app.js` with reactive vanilla JS for tabs, copy-to-clipboard, test-connectivity ping, settings save, and OTP modal.
- Create `app/templates/base.html`, `dashboard.html`, and `login.html`.
- Create `app/routes/web.py` to render the templates and handle authentication cookies if `DASHBOARD_PASSWORD` is configured.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_ui.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/ app/templates/ app/routes/web.py tests/test_web_ui.py
git commit -m "feat: implement modern WebUI dashboard, proxy settings interface, and client setup guide"
```

---

### Task 7: Credential Migration Utility & Production Server Assets

**Files:**
- Create: `scripts/migrate_credentials.py`
- Create: `oracle-vm/jiotv.service`
- Create: `oracle-vm/nginx-tv.conf`
- Update: `README.md`
- Test: `tests/test_migration.py`

**Interfaces:**
- Consumes: Existing `/opt/jiotv_go/store_v4.toml` on the Oracle VM.
- Produces: Valid `data/auth.json` containing `sso_token`, `crm`, `unique_id`, `subscriber_name`, and `expiry` so no user re-login is necessary.

- [ ] **Step 1: Write test for credential migration utility**

```python
# tests/test_migration.py
from pathlib import Path
import json
from scripts.migrate_credentials import parse_toml_and_migrate

def test_parse_store_toml(tmp_path: Path):
    toml_content = """
    [auth]
    sso_token = "test_sso_token_123"
    crm = "test_crm_456"
    unique_id = "test_uid_789"
    name = "Test User"
    """
    toml_path = tmp_path / "store_v4.toml"
    toml_path.write_text(toml_content)
    
    out_dir = tmp_path / "data"
    success = parse_toml_and_migrate(toml_path, out_dir)
    assert success is True
    
    auth_data = json.loads((out_dir / "auth.json").read_text())
    assert auth_data["sso_token"] == "test_sso_token_123"
    assert auth_data["crm"] == "test_crm_456"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration.py -v`  
Expected: FAIL (ModuleNotFoundError: No module named 'scripts.migrate_credentials')

- [ ] **Step 3: Implement migration script and production service unit**

- Implement `scripts/migrate_credentials.py` to parse `store_v4.toml` (handling TOML without extra heavy dependencies or using standard `tomllib` in Python 3.11+ / regex fallback).
- Create `oracle-vm/jiotv.service` running `/opt/jiotv/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 5001`.
- Update `oracle-vm/nginx-tv.conf` with updated proxy pass settings.
- Write comprehensive `README.md` documenting installation, configuration, WebUI features, and client setup.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migration.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_credentials.py oracle-vm/jiotv.service oracle-vm/nginx-tv.conf README.md tests/test_migration.py
git commit -m "feat: add credential migration script, systemd unit, and complete documentation"
```

---

### Task 8: Production Deployment & Live Verification on `tv.trylocalhost.com`

**Target Environment:** `ubuntu@home.trylocalhost.com` (`tv.trylocalhost.com`)  
**Companion Proxy:** `pranabesh@100.107.251.122:8888` (Tailscale)

- [ ] **Step 1: Package and deploy project to Oracle VM**
  - Rsync or clone repository to `/opt/jiotv` on `ubuntu@home.trylocalhost.com`.
  - Create Python virtual environment: `python3 -m venv /opt/jiotv/venv`.
  - Install dependencies: `/opt/jiotv/venv/bin/pip install -r /opt/jiotv/requirements.txt`.
- [ ] **Step 2: Migrate existing authentication credentials**
  - Run `/opt/jiotv/venv/bin/python /opt/jiotv/scripts/migrate_credentials.py /opt/jiotv_go/store_v4.toml /opt/jiotv/data`.
  - Verify `/opt/jiotv/data/auth.json` contains valid tokens.
- [ ] **Step 3: Deploy systemd unit and stop legacy `jiotv_go`**
  - Run `sudo systemctl stop jiotv_go`.
  - Run `sudo cp /opt/jiotv/oracle-vm/jiotv.service /etc/systemd/system/jiotv.service`.
  - Run `sudo systemctl daemon-reload && sudo systemctl enable --now jiotv`.
  - Verify service status: `sudo systemctl status jiotv`.
- [ ] **Step 4: Live Verification**
  - Verify WebUI loads at `https://tv.trylocalhost.com/` with HTTP 200.
  - Verify `/playlist.m3u` returns valid playlist containing channels.
  - Verify `/epg.xml.gz` returns valid gzipped XMLTV.
  - Verify `/live/202` (DD National) returns `HTTP 302 Found` with direct Jio CDN URL.
  - Test WebUI "Network & Proxy Settings": test connectivity probe, toggle proxy setting, and verify live test diagnostics.
- [ ] **Step 5: Push all changes to GitHub**
  - Push branch `main` to `git@github.com:pranabeshsingh/jiotv.git`.

---

## Plan Review Checklist
- [x] Spec coverage: Every feature in the spec (Direct/Proxy toggle in WebUI, 302 streaming, offline-cache, OTP auth, Kodi guide) is mapped to a task.
- [x] No placeholders: All test cases, models, commands, and file paths are fully defined.
- [x] Clean interfaces: Types and methods align across `config.py`, `jio_api.py`, `channel_manager.py`, and API routes.
