# Custom JioTV IPTV Server Design Specification

**Date:** 2026-10-04  
**Status:** Draft for Review  
**Target Git Repo:** `git@github.com:pranabeshsingh/jiotv.git`  
**Target Deployment:** Oracle Cloud VM (`tv.trylocalhost.com`) & Local / Self-Hosted  

---

## 1. Executive Summary

This project replaces the Go-based `jiotv_go` server with a lightweight, robust, native Python (FastAPI) IPTV server tailored for JioTV.

The server exposes standard IPTV interfaces (M3U playlist and XMLTV EPG) for media clients like Kodi (via PVR IPTV Simple Client), TiviMate, and VLC, with direct CDN stream redirection to minimize server bandwidth and CPU usage. It features an offline-first caching architecture so clients remain fully functional even when upstream connections or companion proxies are offline.

Critically, **proxy configuration (Tailscale or any residential proxy) is entirely optional**:
- If deployed on a residential connection or an unblocked ISP, it operates in **Direct Mode** with zero proxy setup.
- If deployed on cloud infrastructure (such as Oracle Cloud Free Tier) where Jio's Fastly CDN blocks datacenter IPs with `HTTP 450`, users can configure, test, and toggle an **Upstream Residential Proxy** directly through the modern WebUI or `.env`, without restarting the service.

---

## 2. Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FastAPI IPTV Server                              │
│                (Deployable on VPS, Docker, or Local Machine)                │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        Modern WebUI Dashboard                         │  │
│  │  • Status & Account Info       • One-Click OTP Login Modal            │  │
│  │  • Client Setup Guide (Kodi)   • Channel Catalog Browser              │  │
│  │  • Network & Proxy Settings (Toggle Direct vs Proxy + Test Reachable) │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │                                      │
│  ┌────────────────────────┐  ┌───────▼─────────────┐  ┌──────────────────┐  │
│  │      IPTV Engine       │  │   Channel Manager   │  │ Jio API Client   │  │
│  │  • /playlist.m3u       │  │  • Offline SQLite / │  │ • Auth / OTP     │  │
│  │  • /epg.xml.gz         │  │    JSON Cache       │  │ • Direct Playback│  │
│  │  • /live/{id} (302)    │  │  • Auto-Sync Engine │  │ • Key / License  │  │
│  └───────────┬────────────┘  └───────▲─────────────┘  └────────┬─────────┘  │
└──────────────┼───────────────────────┼─────────────────────────┼────────────┘
               │                       │                         │
      Direct 302 Redirect              │ Outbound Catalog / EPG  │ Direct 16ms API
      to Client                        │ Sync Request            │ (Not blocked)
               │                       │                         │
               ▼                       ▼                         ▼
┌──────────────────────────┐   ┌────────────────────────┐  ┌───────────────────┐
│     Home TV / Kodi       │   │ Network Routing Mode   │  │ Jio Playback API  │
│  (PVR IPTV Simple Client)│   │                        │  │ (jiotvapi.media)  │
│                          │   │ [Direct Mode]          │  └───────────────────┘
│ • Hardware Decoding      │   │ ──► Direct to Jio CDN  │
│ • Direct CDN Playback    │   │                        │
│ • Inputstream.adaptive   │   │ [Proxy Mode (Opt-in)]  │
└──────────────────────────┘   │ ──► Residential Proxy  │
                               │     (e.g. Tailscale /  │
                               │      homeserver)       │
                               └────────────────────────┘
```

### Routing Rules
1. **Live Stream Playback (`/live/{channel_id}`)**:
   * Calls `https://jiotvapi.media.jio.com/playback/apis/v1.1/geturl` with the subscriber's auth tokens.
   * This API is **never blocked by Fastly** and responds with ~16ms latency directly from cloud VMs.
   * Returns an `HTTP 302 Found` redirect to the signed `.m3u8` or `.mpd` master manifest. The client (Kodi/VLC) streams high-bandwidth video directly from Jio/Akamai CDNs. Zero stream bandwidth traverses the Python server.
2. **Channel Catalog & EPG Metadata Sync**:
   * Calls `https://jiotv.data.cdn.jio.com/apis/v1.4/getallchannel.php`.
   * **In Direct Mode**: Connects directly to Jio CDN.
   * **In Proxy Mode**: Connects through the configured HTTP/SOCKS5 proxy (e.g. `http://100.107.251.122:8888`).
   * **Offline Cache Fallback**: If the upstream sync fails (due to network outage or proxy offline), the server immediately falls back to disk cache. Client playlist requests **never fail**.

---

## 3. Configuration & State Management

### 3.1 Environment Variables (`.env`)
Secrets and initial server parameters are loaded from `.env` via `pydantic-settings`. A documented template `.env.example` is committed to git; `.env` itself is ignored in `.gitignore`.

```ini
# Server Binding
HOST=0.0.0.0
PORT=5001
BASE_URL=https://tv.trylocalhost.com

# Security
DASHBOARD_PASSWORD=change_this_to_a_secure_password
SECRET_KEY=generate_random_secret_for_sessions

# Optional Upstream Proxy (Can also be configured via WebUI)
# Leave empty for Direct Mode (default)
PROXY_ENABLED=false
PROXY_URL=http://100.107.251.122:8888

# Storage Directory
DATA_DIR=./data
```

### 3.2 Persistent Data Directory (`./data/`)
All mutable runtime state is stored in `./data/`:
* `auth.json`: Jio subscriber tokens, refresh tokens, CRM credentials, and expiry timestamps.
* `settings.json`: Runtime configuration overrides (proxy toggle, proxy URL, favorite channel filters) saved via the WebUI without requiring server restarts.
* `channels.json`: Cached channel catalog, genre maps, language codes, and stream quality metadata.
* `epg.xml.gz`: Cached compressed XMLTV guide data.

---

## 4. Endpoints & API Specification

### 4.1 IPTV Interfaces (Client-Facing)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/playlist.m3u` | GET | Full M3U playlist with Kodi metadata (`tvg-id`, `tvg-logo`, `group-title`, `catchup`). Supports query filters: `?lang=Hindi`, `?genre=Entertainment`, `?quality=hd`. |
| `/epg.xml.gz` | GET | Gzipped XMLTV program guide matching `tvg-id`s. |
| `/live/{channel_id}` | GET | Resolves signed stream URL from Jio and issues an `HTTP 302` redirect to the client. |
| `/render/key/{channel_id}` | GET/POST | Widevine license proxy for DRM-protected channels (if requested by Kodi `inputstream.adaptive`). |

### 4.2 WebUI & Management Endpoints
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | GET | Admin dashboard & setup portal (HTML). |
| `/login` | GET/POST | Password authentication for dashboard management. |
| `/api/status` | GET | Health, Jio account status, token expiry, catalog channel count, proxy connectivity. |
| `/api/settings` | GET/POST | Read or update runtime settings (proxy enable/disable, proxy URL). |
| `/api/test-connectivity` | POST | Live probe testing Jio CDN reachability (Direct vs Proxied) and latency. |
| `/api/auth/otp/send` | POST | Trigger Jio SMS OTP (`{"mobile": "+91..."}`). |
| `/api/auth/otp/verify` | POST | Verify OTP (`{"mobile": "+91...", "otp": "..."}`) and save credentials. |
| `/api/sync` | POST | Manually trigger channel catalog and EPG refresh. |
| `/api/channels` | GET | JSON list of channels with search & filter capabilities for the WebUI browser. |

---

## 5. WebUI Design & User Experience

The WebUI will feature a sleek, modern, responsive dark theme (slate/charcoal background, glassmorphism card panels, clear status badges, and interactive copy buttons).

### Key Views & Panels
1. **System Health & Account Banner**:
   * Jio Subscriber status (Name, Mobile, Plan expiration badge).
   * Token refresh countdown with a manual "Refresh Token" button.
   * Total channels loaded, last EPG sync timestamp.
2. **Network & Proxy Settings Card**:
   * Visual indicator: `[Direct Connection Active]` (Green) or `[Proxy Active: 100.107.251.122:8888]` (Blue).
   * Toggle: **"Use Upstream Residential Proxy for CDN Sync"** (On/Off).
   * Proxy URL text input (e.g. `http://100.107.251.122:8888`).
   * **"Test Connection" button**: Immediately pings both Jio Playback and Jio CDN endpoints, outputting response times and status codes (e.g. `Jio CDN: 200 OK (85ms)` vs `HTTP 450 Blocked`).
   * "Save Settings" button: Immediately persists changes to `data/settings.json` and updates the active HTTP client without restarting.
   * Collapsible helper: **"When do I need a proxy?"** Explains that cloud VMs (Oracle/AWS) require a residential proxy (e.g. Tailscale to home PC) due to Jio Fastly 450 blocks, whereas home servers or local networks do not. Provides the 3-line standalone proxy script for easy copy-pasting.
3. **Client Setup Guide (Kodi / TiviMate / VLC)**:
   * Dynamically formats URLs using the current host (`https://tv.trylocalhost.com/playlist.m3u`).
   * Copy-to-clipboard buttons for Playlist URL and EPG URL.
   * Step-by-step Kodi setup instructions (install PVR IPTV Simple Client, enter URLs, enable inputstream.adaptive).
4. **Channel Catalog Explorer**:
   * Filterable grid by Language (Hindi, English, Bengali, Tamil, etc.), Genre (News, Sports, Entertainment), and Resolution (HD / SD).
   * Instant search input.
   * Play button opening channel directly in browser or VLC URI scheme (`vlc://...`).
5. **Jio OTP Login Modal**:
   * Form with mobile number input, "Send OTP" button, countdown timer, and 6-digit OTP confirmation.
   * Handles re-authentication seamlessly from the browser.

---

## 6. Project Structure

```text
jiotv/
├── .env.example               # Template environment configuration
├── .gitignore                  # Ignores .env, data/, __pycache__, venv
├── requirements.txt            # fastapi, uvicorn, httpx, jinja2, pydantic-settings
├── README.md                   # Complete setup, architecture, and deployment guide
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application factory & lifespan
│   ├── config.py               # Settings loader (.env + data/settings.json)
│   ├── jio_api.py              # Jio Auth, OTP, token refresh, and stream resolver
│   ├── channel_manager.py      # Catalog fetching, caching, M3U & EPG generation
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── iptv.py             # /playlist.m3u, /epg.xml.gz, /live/{id}
│   │   ├── api.py              # Status, settings, test-connectivity, auth endpoints
│   │   └── web.py              # Dashboard HTML view & login
│   ├── static/
│   │   ├── css/style.css       # Premium modern dark UI stylesheet
│   │   └── js/app.js           # Client-side reactivity, OTP modal, test ping
│   └── templates/
│       ├── base.html           # Base layout
│       ├── dashboard.html      # Main dashboard with all tabs & settings
│       └── login.html          # Admin login screen
├── data/                       # Git-ignored persistent state
│   ├── .gitkeep
│   ├── auth.json               # (Auto-generated / migrated from store_v4.toml)
│   ├── settings.json           # Runtime settings
│   └── channels.json           # Offline catalog cache
├── oracle-vm/                  # Deployment assets for Oracle Cloud VM
│   ├── jiotv.service           # Systemd unit for the FastAPI server
│   ├── nginx-tv.conf           # Nginx reverse proxy with SSL & caching
│   └── 99-disable-ipv6.conf    # Oracle Cloud IPv6 fix
└── homeserver/                 # Optional companion proxy assets
    ├── jio_proxy.py            # Standalone proxy binding to residential interface
    ├── jiotv-proxy.service     # Systemd user service unit
    └── setup-homeserver.sh     # Quick installer for companion proxy
```

---

## 7. Migration & Deployment Strategy

1. **Local Development & Validation**:
   * Implement FastAPI application in `/Users/pranabesh/code/jiotv`.
   * Unit test Jio API client, M3U generator, and proxy routing logic.
2. **Credential Migration**:
   * Write an automated migration utility that reads the existing authenticated session from `/opt/jiotv_go/store_v4.toml` on the Oracle VM and populates `data/auth.json`, so no new OTP is required during deployment.
3. **Oracle Cloud VM Deployment**:
   * Deploy code to `/opt/jiotv` on `ubuntu@home.trylocalhost.com`.
   * Create Python venv and install dependencies.
   * Replace `jiotv_go.service` with `jiotv.service`.
   * Restart Nginx and verify `https://tv.trylocalhost.com/` serves the WebUI, M3U, and live streams.
4. **Git Version Control**:
   * Commit all code, documentation, and deployment files to `git@github.com:pranabeshsingh/jiotv.git`.
   * Verify that `.env` and `data/` credentials are not tracked.

---

## 8. Verification & Acceptance Criteria

1. **Direct vs Proxy Switchability**:
   * Changing the proxy toggle in WebUI persists to `data/settings.json`.
   * "Test Connection" button gives real-time diagnostic output for both direct and proxied connections.
2. **Offline-First Resilience**:
   * With the upstream proxy offline, `/playlist.m3u` and `/epg.xml.gz` continue to return HTTP 200 with full channel listings from local cache.
3. **Streaming Quality & Bandwidth**:
   * `/live/{channel_id}` returns `HTTP 302 Found` pointing directly to Jio CDN.
   * Kodi on home TV connects directly to Jio CDN without proxying video packets through the Oracle VM.
4. **Security**:
   * Admin dashboard endpoints require authentication if `DASHBOARD_PASSWORD` is set.
   * Sensitive tokens are never leaked in public API responses or committed to git.
