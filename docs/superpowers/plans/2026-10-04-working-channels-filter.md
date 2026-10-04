# Working Channels Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement account entitlement detection and channel filtering to provide a "working channels only" playlist (`/playlist_working.m3u` and `?filter=working`) that excludes paywalled channels (Sony SAB, Star Plus, etc.) for users on base Jio mobile plans.

**Architecture:** Extend `SessionManager` to inspect active user plans from `userservice/apis/v1/plans`. Update `ChannelManager` to pull from the mobile channel list endpoint, populating `business_type` and `is_premium`. Add `working_only` filtering across M3U generator, IPTV routes, and WebUI.

**Tech Stack:** Python 3.10+, FastAPI, httpx, Vanilla JS/CSS, Pytest.

## Global Constraints
- Python 3.10+ compatibility across all changes.
- Never commit `.env` or plain credentials.
- Backward compatibility: Existing `/playlist.m3u` without query parameters remains functional.
- Zero extra dependencies: Use existing standard library and `httpx`.

---

### Task 1: Account Entitlements in `SessionManager`

**Files:**
- Modify: `app/session_manager.py`
- Test: `tests/test_session_manager.py`

**Interfaces:**
- Consumes: `SessionManager._auth_headers()`, `data/credentials.json`
- Produces: `SessionManager.get_entitlements() -> Dict[str, Any]` and `SessionManager.has_premium_entitlement() -> bool`

- [ ] **Step 1: Write the failing test**
Create a test in `tests/test_session_manager.py` that verifies `has_premium_entitlement()` returns `False` for base plan (`planid: "1"`, `business_type: "jio"`) and `True` when a premium plan is present.

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.session_manager import SessionManager
from app.config import Settings

@pytest.mark.asyncio
async def test_has_premium_entitlement(tmp_path):
    settings = Settings(data_dir=tmp_path)
    sm = SessionManager(settings)
    sm._credentials = {
        "ssoToken": "fake_sso",
        "crm": "fake_crm",
        "uniqueId": "fake_uid",
    }
    
    # Base plan only
    mock_base = {"PackageInfo": [{"planid": "1", "package_name": "jio", "business_type": "jio"}]}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_base
        has_prem = await sm.has_premium_entitlement()
        assert has_prem is False

    # Premium plan present
    mock_prem = {"PackageInfo": [{"planid": "1", "package_name": "jio", "business_type": "jio"}, {"planid": "Rs55_30D_JioTV", "package_name": "JioTV Premium", "business_type": "premium"}]}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_prem
        has_prem = await sm.has_premium_entitlement()
        assert has_prem is True
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_session_manager.py -k test_has_premium_entitlement -v`
Expected: FAIL (`AttributeError: 'SessionManager' object has no attribute 'has_premium_entitlement'`)

- [ ] **Step 3: Write minimal implementation in `app/session_manager.py`**
Implement `get_entitlements()` and `has_premium_entitlement()`:
```python
PLANS_API_URL = "https://jiotvapi.media.jio.com/userservice/apis/v1/plans"

async def get_entitlements(self, force: bool = False) -> Dict[str, Any]:
    entitlements_file = self.data_dir / "entitlements.json"
    if not force and entitlements_file.exists():
        try:
            return json.loads(entitlements_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    creds = self.get_credentials()
    if not creds:
        return {}

    headers = {
        "User-Agent": "okhttp/4.9.3",
        "devicetype": "phone",
        "os": "android",
        "ssoToken": creds.get("ssoToken", ""),
        "crm": creds.get("crm", ""),
        "uniqueId": creds.get("uniqueId", ""),
    }
    client_kwargs = {"timeout": 10.0}
    if self.settings.proxy_enabled and self.settings.proxy_url:
        client_kwargs["proxy"] = self.settings.proxy_url

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(PLANS_API_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                self.data_dir.mkdir(parents=True, exist_ok=True)
                entitlements_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return data
    except Exception as e:
        logger.warning(f"Failed to fetch user entitlements: {e}")
    return {}

async def has_premium_entitlement(self) -> bool:
    data = await self.get_entitlements()
    pkg_info = data.get("PackageInfo", [])
    for pkg in pkg_info:
        b_type = str(pkg.get("business_type", "")).lower()
        p_name = str(pkg.get("package_name", "")).lower()
        p_id = str(pkg.get("planid", "")).lower()
        if b_type == "premium" or "premium" in p_name or "rs55" in p_id:
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/pytest tests/test_session_manager.py -k test_has_premium_entitlement -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/session_manager.py tests/test_session_manager.py
git commit -m "feat(auth): add Jio account entitlements detection in SessionManager"
```

---

### Task 2: Catalog Sync & Channel Metadata in `ChannelManager`

**Files:**
- Modify: `app/channel_manager.py`
- Test: `tests/test_channel_manager.py`

**Interfaces:**
- Consumes: Mobile API URL `https://jiotvapi.cdn.jio.com/apis/v3.1/getMobileChannelList/get/?langId=6&os=android&devicetype=phone&usertype=JIO&version=315&langId=6`
- Produces: `business_type`, `is_premium` on channels, and `working_only` parameter in `get_channels()` and `generate_m3u()`

- [ ] **Step 1: Write the failing test**
In `tests/test_channel_manager.py`, add tests checking:
1. `business_type` and `is_premium` are parsed during `sync_channels()`.
2. `get_channels(working_only=True)` excludes channels where `is_premium == True`.

```python
def test_channel_manager_working_filter(channel_manager):
    channel_manager._channels_cache = [
        {"channel_id": 154, "channel_name": "Sony SAB", "business_type": "premium", "is_premium": True},
        {"channel_id": 474, "channel_name": "Sony Pal", "business_type": "free", "is_premium": False},
        {"channel_id": 173, "channel_name": "Aaj Tak", "business_type": "free", "is_premium": False},
        {"channel_id": 100, "channel_name": "Jio Cinema", "business_type": "jio", "is_premium": False},
    ]
    all_channels = channel_manager.get_channels(working_only=False)
    assert len(all_channels) == 4
    
    working_channels = channel_manager.get_channels(working_only=True)
    assert len(working_channels) == 3
    assert not any(c["channel_name"] == "Sony SAB" for c in working_channels)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_channel_manager.py -k test_channel_manager_working_filter -v`
Expected: FAIL (`TypeError: get_channels() got an unexpected keyword argument 'working_only'`)

- [ ] **Step 3: Implement catalog enhancement and filtering in `app/channel_manager.py`**
- Update catalog fetch endpoint with fallback.
- Parse `business_type`:
  ```python
  b_type = (ch.get("business_type") or "free").lower()
  is_premium = (b_type == "premium")
  ```
- Update `get_channels()` and `generate_m3u()` signature:
  ```python
  def get_channels(
      self,
      lang: Optional[str] = None,
      genre: Optional[str] = None,
      search: Optional[str] = None,
      is_hd: Optional[bool] = None,
      working_only: bool = False,
  ) -> List[Dict[str, Any]]:
  ```
  If `working_only`: `filtered = [c for c in filtered if not c.get("is_premium", False)]`.

- [ ] **Step 4: Run tests to verify they pass**
Run: `.venv/bin/pytest tests/test_channel_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/channel_manager.py tests/test_channel_manager.py
git commit -m "feat(catalog): add business_type and working_only channel filtering"
```

---

### Task 3: IPTV & Catalog API Routes

**Files:**
- Modify: `app/routes/iptv.py`
- Test: `tests/test_iptv_routes.py`

**Interfaces:**
- Consumes: `ChannelManager.generate_m3u(working_only=...)`
- Produces:
  - `/playlist.m3u` query `filter=working` (or `working=true`, `filter=free`, `filter=subscribed`)
  - `/playlist_working.m3u` & `/working.m3u`
  - `/api/channels` query `filter=working`

- [ ] **Step 1: Write the failing test**
In `tests/test_iptv_routes.py`:
```python
def test_playlist_working_endpoints(client, channel_manager):
    channel_manager._channels_cache = [
        {"channel_id": 154, "channel_name": "Sony SAB", "business_type": "premium", "is_premium": True},
        {"channel_id": 474, "channel_name": "Sony Pal", "business_type": "free", "is_premium": False},
    ]
    # Query param filter
    r1 = client.get("/playlist.m3u?filter=working")
    assert r1.status_code == 200
    assert "Sony Pal" in r1.text
    assert "Sony SAB" not in r1.text

    # Dedicated working endpoint
    r2 = client.get("/playlist_working.m3u")
    assert r2.status_code == 200
    assert "Sony Pal" in r2.text
    assert "Sony SAB" not in r2.text

    # JSON API filter
    r3 = client.get("/api/channels?filter=working")
    assert r3.status_code == 200
    data = r3.json()
    assert len(data) == 1
    assert data[0]["channel_name"] == "Sony Pal"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_iptv_routes.py -k test_playlist_working_endpoints -v`
Expected: FAIL (404 on `/playlist_working.m3u` or Sony SAB present)

- [ ] **Step 3: Implement routes in `app/routes/iptv.py`**
- Update `/playlist.m3u` to check `filter == "working"` or `working in ("true", "1")` or `filter in ("free", "subscribed")`.
- Add routes for `/playlist_working.m3u` and `/working.m3u` delegating to `generate_m3u(working_only=True)`.
- Update `/api/channels` to accept `filter: Optional[str] = None` and pass `working_only` to `get_channels()`.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/pytest tests/test_iptv_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/routes/iptv.py tests/test_iptv_routes.py
git commit -m "feat(routes): add /playlist_working.m3u and working filter to IPTV endpoints"
```

---

### Task 4: WebUI Client Setup & Channel Filter UI

**Files:**
- Modify: `app/templates/dashboard.html`
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: `/api/channels?filter=working`, `/playlist_working.m3u`
- Produces:
  - Setup tab: "Working Channels Only" playlist URL with Copy button.
  - Channel Catalog tab: "Working Only" filter button and badges on channel cards.
  - Status tab: Account plan tier indicator.

- [ ] **Step 1: Update `dashboard.html`**
- Add the "Working Channels Only (Recommended for TV clients)" playlist URL box alongside All Channels in the Client Setup tab.
- Add filter buttons (`All Channels`, `Working Only`, `Premium`) above channel grid.
- Add account entitlement status indicator in the Status tab.

- [ ] **Step 2: Update `static/js/app.js`**
- Render channel cards with green `Included` badge or orange `Requires JioTV Premium` badge.
- Handle clicking the "Working Only" filter chip to reload or filter channels dynamically.
- Support 1-click copying for both playlist URLs.

- [ ] **Step 3: Verify local static files and styling**
Run: `.venv/bin/ruff check .`
Ensure no syntax or lint errors.

- [ ] **Step 4: Commit**
```bash
git add app/templates/dashboard.html app/static/js/app.js
git commit -m "feat(ui): add working channels filter, playlist copy box, and premium badges"
```

---

### Task 5: Full Test Suite, Git Push & Deployment

**Files:**
- Test: Full test suite (`pytest`)
- Code: Cleanliness and linting (`ruff`)

- [ ] **Step 1: Run full pytest suite**
Run: `.venv/bin/pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Run ruff check**
Run: `.venv/bin/ruff check .`
Expected: 0 errors.

- [ ] **Step 3: Push commits to GitHub**
Run: `git push origin main`

- [ ] **Step 4: Deploy to Oracle VM (`tv.trylocalhost.com`)**
SSH into `ubuntu@home.trylocalhost.com`:
- `cd /opt/jiotv && sudo git pull`
- `sudo systemctl restart jiotv`
- Verify `curl -I https://tv.trylocalhost.com/playlist_working.m3u` returns HTTP 200.
