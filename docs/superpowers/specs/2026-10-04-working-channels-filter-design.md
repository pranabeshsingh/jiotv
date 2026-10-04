# Working Channels Filter & Account Entitlements Design

## 1. Overview
JioTV paywalls several major broadcaster channels (e.g. Sony SAB, Sony Entertainment Television, Sony Ten, Star Plus, Star Sports, Colors, Zee) under a separate "JioTV Premium" add-on pack. When an account with only the standard Jio mobile plan (`package_id: 1`) requests playback for these channels, Jio's playback API returns `HTTP 403 {"code": 3012, "message": "No eligible plans found"}`.

In contrast, ~1,007 channels (Free-to-air, News, Devotional, Regional, and standard Jio-tier channels such as Sony Pal, Sony Wah, Aaj Tak, NDTV, DD channels) stream without additional subscriptions.

This feature introduces dynamic account entitlement detection and filtered playlist/catalog options so IPTV clients (Kodi, TiviMate, OTT Navigator) can subscribe to only working channels, eliminating 403 errors during channel surfing.

---

## 2. Architecture & Components

### 2.1 Jio Account Entitlements (`SessionManager`)
- **API Endpoint**: `https://jiotvapi.media.jio.com/userservice/apis/v1/plans`
- **Method**: GET
- **Headers**:
  - `User-Agent`: `okhttp/4.9.3`
  - `devicetype`: `phone`
  - `os`: `android`
  - `ssoToken`: `<active_sso_token>`
  - `crm`: `<crm_token>`
  - `uniqueId`: `<unique_id>`
- **Response Structure**:
  ```json
  {
    "PackageInfo": [
      {
        "planid": "1",
        "package_name": "jio",
        "business_type": "jio"
      }
    ]
  }
  ```
- **Entitlement Evaluation**:
  - Base plan only (`planid: 1`, `business_type: "jio"`): `has_premium = False`.
  - Additional packages containing premium business types or partner IDs (e.g. `Rs55_30D_JioTV`): `has_premium = True`.
- **Caching**: Stored in `data/entitlements.json` alongside session credentials, refreshed during login or token refresh.

---

### 2.2 Channel Catalog Sync (`ChannelManager`)
- **API Endpoint**: `https://jiotvapi.cdn.jio.com/apis/v3.1/getMobileChannelList/get/?langId=6&os=android&devicetype=phone&usertype=JIO&version=315&langId=6`
- **Headers**:
  - `User-Agent`: `okhttp/4.9.3`
  - `devicetype`: `phone`
  - `os`: `android`
  - `appkey`: `NzNiMDhlYzQyNjJm`
  - `lbcookie`: `1`
  - `usertype`: `JIO`
- **Normalization Fields**:
  - `channel_id` (int)
  - `channel_name` (str)
  - `language` (str)
  - `genre` (str)
  - `logo` (str)
  - `is_hd` (bool)
  - `business_type` (str): `"free"` | `"jio"` | `"premium"` | `"guest"`
  - `is_premium` (bool): `True` if `business_type.lower() == "premium"` else `False`
- **Fallback**: Fallback to `https://jiotv.data.cdn.jio.com/apis/v1.4/getallchannel.php` if mobile endpoint is unavailable.

---

### 2.3 Playlist & Catalog Filtering (`ChannelManager` & `app/routes/iptv.py`)
- **Method**: `ChannelManager.get_channels(working_only: bool = False, ...)`
- **Evaluation**:
  - If `working_only` is False: return all channels.
  - If `working_only` is True:
    - If account has `has_premium == True`: return all channels.
    - If account has `has_premium == False`: filter out channels where `is_premium == True` (i.e. `business_type == "premium"`).
- **M3U Endpoints**:
  - `/playlist.m3u`:
    - Accepts `?filter=working` (or `?filter=subscribed`, `?working=true`, `?free=true`).
  - `/playlist_working.m3u` & `/working.m3u`:
    - Direct route serving only working channels.
  - `/api/channels`:
    - Accepts `?filter=working` to return filtered JSON for WebUI.

---

### 2.4 WebUI Enhancements (`dashboard.html` & `static/js/app.js`)
- **Client Setup Card**:
  - Primary URL: All Channels (`/playlist.m3u`).
  - Working Only URL: Working Channels (`/playlist_working.m3u`).
  - 1-click copy buttons for both.
- **Channel Browser Card**:
  - Filter chips: `All Channels`, `Working / Included`, `Requires Premium`.
  - Badges on cards:
    - Green badge: `Included` (for `free`, `jio`, `guest`)
    - Amber/Orange badge: `Requires JioTV Premium` (for `premium`)
- **Status Dashboard**:
  - Display account plan level: `Jio Mobile Base Plan` or `JioTV Premium Active`.

---

## 3. Error Handling & Edge Cases
1. **Unauthenticated Server**: If no credentials exist, assume base plan (`has_premium = False`), allowing `working_only` to serve free-to-air/Jio channels.
2. **Entitlements API Failure**: If Jio's plans endpoint fails or times out, fallback to last cached entitlements or assume base plan.
3. **Empty Filter Result**: If filter removes all channels (should never happen as there are >1,000 free channels), log a warning and return empty playlist rather than crash.

---

## 4. Verification Plan
- Unit test `test_account_entitlements_detection`: Mock base vs premium plan responses.
- Unit test `test_channel_manager_working_filter`: Test channel filtering with and without premium plan.
- Integration test `test_playlist_working_m3u_endpoint`: Test `/playlist_working.m3u` and `/playlist.m3u?filter=working`.
- Integration test `test_channels_api_working_filter`: Test `/api/channels?filter=working`.
- WebUI verification: Check filter chips and playlist copy cards in browser.
