# Kodi Client Configuration Guide

This guide details how to configure **Kodi** on your Smart TV, Android TV, Firestick, Apple TV, or PC to stream JioTV channels via your server.

---

## 1. Prerequisites on Kodi

1. **InputStream Adaptive** (Required for Widevine DRM channels):
   * Included with Kodi v19+. Ensure it is enabled in **Settings** > **Add-ons** > **VideoPlayer InputStream** > **InputStream Adaptive**.
2. **InputStream Helper** (Optional, recommended):
   * Auto-installs/updates Widevine CDM libraries if running Kodi on Linux/Android/Raspberry Pi.

---

## 2. Configure PVR IPTV Simple Client

1. Open Kodi and navigate to:
   * **Settings** > **Add-ons** > **Install from repository** > **PVR clients** > **IPTV Simple Client** > Click **Install**.
2. Once installed, open **IPTV Simple Client settings** (click **Configure**).

### A. General Tab (Playlist)
* **Location**: `Remote path (Internet address)`
* **M3U Playlist URL**:
  ```text
  https://tv.trylocalhost.com/playlist.m3u
  ```
  *(Or `https://tv.trylocalhost.com/channels?type=m3u`)*
* **Cache M3U at local storage**: `Enabled` (recommended)

### B. EPG Tab (TV Guide)
* **Location**: `Remote path (Internet address)`
* **XMLTV URL**:
  ```text
  https://tv.trylocalhost.com/epg.xml.gz
  ```
* **EPG Time Shift**: `0` (or your timezone if offset)
* **Apply Time Shift to All Channels**: `Disabled`

### C. Channel Logos
* Logos are automatically supplied via the M3U `#EXTINF` tags pointing to `https://tv.trylocalhost.com/jtvimage/`. No manual path needed.

---

## 3. Apply and Watch

1. Click **OK** in the IPTV Simple Client configuration.
2. If prompted, restart Kodi or clear PVR data via **Settings** > **PVR & Live TV** > **General** > **Clear data**.
3. Return to the home screen and click **TV** (or **Live TV**).
4. Browse channels, view the Electronic Program Guide, and click to stream.
