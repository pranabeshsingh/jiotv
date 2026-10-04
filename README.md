# JioTV Headless IPTV Server & Kodi Streaming Engine

A modern, lightweight, self-hosted IPTV server for **JioTV** built with Python (FastAPI). It streams live TV channels directly to **Kodi** (via PVR IPTV Simple Client), **TiviMate**, and **VLC** with zero server video bandwidth usage, an offline-first cache, and a rich WebUI dashboard.

---

## Architecture & How It Works

```
                       ┌──────────────────────────────────────────────┐
                       │          Oracle Cloud Free Tier VM           │
                       │             (tv.trylocalhost.com)            │
                       │                                              │
                       │  • Python FastAPI Server (Port 5001)         │
                       │  • Nginx Reverse Proxy (SSL + Stale Cache)   │
                       │  • WebUI Dashboard & IPTV M3U/EPG Endpoints  │
                       └───────┬──────────────────────────────▲───────┘
        HTTPS M3U & EPG        │                              │ Outbound Metadata
     (Offline-First Cache)     │                              │ Sync (Optional)
                               ▼                              │ (e.g. Tailscale Proxy)
 ┌──────────────────────────────────────────────┐             │
 │            Home Smart TV (Kodi)              │             │
 │        PVR IPTV Simple Client                │             │
 │                                              │             │
 │ • Fetches M3U Playlist & EPG                 │             │
 │ • Hardware HEVC / H.264 video decoding       │             │
 │ • Decrypts Widevine DRM via local CDM        │             │
 └─────────────────────┬────────────────────────┘             │
                       │                                      │
                       │ Direct Stream Video Chunks           │
                       │ (HTTP 302 Redirect to CDN)           │
                       │                                      │
                       ▼                                      │
 ┌──────────────────────────────────────────────┐    ┌────────┴─────────────────────┐
 │          Jio / Akamai CDN Edge Nodes         │    │ Optional Residential Proxy   │
 │      (High-bandwidth video chunks)           │    │ (Homeserver / Tailscale)     │
 │                                              │    │                              │
 │ • TV downloads stream data directly          │    │ • Only needed for cloud hosts│
 │ • Server bandwidth consumption: 0 MB         │    │ • Bypasses Fastly 450 blocks │
 └──────────────────────────────────────────────┘    └──────────────────────────────┘
```

### Key Engineering Highlights
1. **Zero Server Bandwidth (HTTP 302 Passthrough)**:
   * The server only issues authentication and metadata tokens.
   * Playback requests (`/live/{id}`) return an `HTTP 302 Found` redirecting your TV client directly to signed Jio/Akamai CDN edge nodes.
   * Multi-megabit video streams flow directly between your home TV and Jio's CDN. Server CPU and bandwidth usage remain near zero.
2. **Direct Mode vs. Optional Residential Proxy**:
   * **Direct Mode (Default)**: If running on a home server, Raspberry Pi, or local residential ISP, no proxy is needed. Jio connections work directly.
   * **Proxy Mode (Opt-in via WebUI)**: Jio's Fastly CDN blocks cloud datacenters (Oracle Cloud, AWS, DigitalOcean) with `HTTP 450` for channel catalog updates. In the WebUI **Network & Proxy Settings**, you can toggle upstream proxying on/off, set the address (e.g. `http://100.107.251.122:8888` over Tailscale), and test reachability with one click.
3. **Offline-First Resilience**:
   * Channel catalogs, categories, logos, and EPG data are persistently cached on disk (`data/channels.json` and `data/epg.xml.gz`).
   * If your upstream connection or companion proxy goes offline, the server continues serving the local cache. Clients never experience 500 errors or dropped playlists.
4. **Interactive WebUI**:
   * Dark modern dashboard with live service metrics and subscriber information.
   * Built-in Jio SMS OTP login and token refresh.
   * Real-time network reachability diagnostic probe.
   * Copy-to-clipboard buttons for M3U and EPG URLs with setup instructions.
   * Filterable channel catalog with language, genre, and search filters.

---

## Directory Structure

```text
jiotv/
├── .env.example               # Template environment configuration (secrets never committed)
├── .gitignore                 # Ignores .env, data/, venv, logs
├── requirements.txt           # Python dependencies (FastAPI, Uvicorn, HTTPX)
├── README.md                  # This documentation
├── app/
│   ├── main.py                # FastAPI application entry point & lifespan
│   ├── config.py              # Configuration loader (.env + data/settings.json)
│   ├── jio_api.py             # Jio authentication, OTP, token refresh, and stream resolver
│   ├── channel_manager.py     # Channel catalog manager, offline cache, M3U & EPG engine
│   ├── routes/
│   │   ├── iptv.py            # /playlist.m3u, /epg.xml.gz, /live/{channel_id}
│   │   ├── api.py             # REST endpoints for status, settings, diagnostics, and auth
│   │   └── web.py             # WebUI views, templates, and dashboard login
│   ├── static/
│   │   ├── css/style.css      # Premium dark theme stylesheet
│   │   └── js/app.js          # Dynamic UI interactivity, test ping, and OTP modal
│   └── templates/
│       ├── base.html          # Base layout
│       ├── dashboard.html     # Main dashboard interface
│       └── login.html         # Admin authentication view
├── data/                      # Persistent runtime state (Git ignored)
│   ├── auth.json              # Jio subscriber tokens (migrated or authenticated)
│   ├── settings.json          # Runtime overrides saved from WebUI
│   ├── channels.json          # Cached channels list
│   └── epg.xml.gz             # Compressed XMLTV guide data
├── scripts/
│   └── migrate_credentials.py # Migrates legacy store_v4.toml to auth.json
├── oracle-vm/
│   ├── jiotv.service          # Systemd service unit for the FastAPI server
│   ├── nginx-tv.conf          # Nginx virtual host with SSL & stale cache
│   └── 99-disable-ipv6.conf   # Fix for Oracle Cloud IPv6 route hang
└── homeserver/
    ├── jio_proxy.py           # Optional companion proxy binding to physical interface
    └── jiotv-proxy.service    # User systemd service unit for homeserver
```

---

## Deployment & Setup Guide

### 1. Server Installation (Oracle Cloud VM / VPS / Local)

```bash
# Clone the repository
git clone git@github.com:pranabeshsingh/jiotv.git /opt/jiotv
cd /opt/jiotv

# Create Python virtual environment
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
nano .env
```

Edit `.env`:
```ini
HOST=0.0.0.0
PORT=5001
BASE_URL=https://tv.trylocalhost.com
DASHBOARD_PASSWORD=your_secure_password
SECRET_KEY=generate_random_secret_string
PROXY_ENABLED=false
DATA_DIR=./data
```

### 2. Migrating Existing Credentials (No Re-login Required)

If migrating from an existing `jiotv_go` installation:
```bash
./venv/bin/python scripts/migrate_credentials.py /opt/jiotv_go/data/store_v4.toml /opt/jiotv/data
```
This automatically converts your active session tokens into `data/auth.json` and copies any cached channels and EPG files.

### 3. Setting Up Systemd Service

```bash
sudo cp oracle-vm/jiotv.service /etc/systemd/system/jiotv.service
sudo systemctl daemon-reload
sudo systemctl enable --now jiotv
sudo systemctl status jiotv
```

### 4. Optional: Companion Residential Proxy (If in Cloud Datacenter)

If hosting on Oracle Cloud or AWS, Jio Fastly blocks channel catalog downloads (`HTTP 450`). To bypass this:
1. Run `homeserver/jio_proxy.py` on any residential computer connected to Tailscale:
   ```bash
   python3 homeserver/jio_proxy.py
   ```
2. Open your WebUI at `https://tv.trylocalhost.com/`, go to **Network & Proxy Settings**, toggle **Use Upstream Residential Proxy**, enter your Tailscale IP (e.g. `http://100.107.251.122:8888`), and click **Test Connection** followed by **Save Settings**.

---

## Client Setup (Kodi, TiviMate, VLC)

### Kodi Setup (PVR IPTV Simple Client)
1. Open Kodi ➔ **Settings** ➔ **Add-ons** ➔ **Install from repository** ➔ **PVR clients** ➔ **PVR IPTV Simple Client** ➔ **Install**.
2. Go to **Configure Add-on**:
   * **General**:
     * Location: `Remote Path (Internet address)`
     * M3U Play List URL: `https://tv.trylocalhost.com/playlist.m3u`
   * **EPG**:
     * XMLTV URL: `https://tv.trylocalhost.com/epg.xml.gz`
   * **Catchup**:
     * Enabled: `Yes`
3. Ensure **InputStream Adaptive** is enabled in **VideoPlayer InputStream** add-ons.
4. Restart Kodi. All channels and TV guide information will load automatically.

### M3U Query Filtering
You can filter channels in the playlist URL directly:
* By Language: `https://tv.trylocalhost.com/playlist.m3u?lang=Hindi`
* By Multiple Languages: `https://tv.trylocalhost.com/playlist.m3u?lang=Hindi,Bengali,English`
* By Category: `https://tv.trylocalhost.com/playlist.m3u?genre=News`
* High Definition only: `https://tv.trylocalhost.com/playlist.m3u?is_hd=true`

---

## Security & Secrets
- Never commit `.env` or `data/` to git.
- Protect the WebUI dashboard by setting `DASHBOARD_PASSWORD` in `.env`.
- Live streams and M3U playlists remain accessible to media clients without password prompts.
