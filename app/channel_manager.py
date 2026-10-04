import gzip
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

MOBILE_CHANNELS_URL = "https://jiotvapi.cdn.jio.com/apis/v3.1/getMobileChannelList/get/?langId=6&os=android&devicetype=phone&usertype=JIO&version=315&langId=6"
CDN_DATA_URL = "https://jiotv.data.cdn.jio.com/apis/v1.4/getallchannel.php"
IMAGE_BASE_URL = "https://jiotv.catchup.cdn.jio.com/dare_images/images/"

CATEGORY_MAP = {
    0: "General",
    5: "Entertainment",
    6: "Movies",
    7: "Kids",
    8: "Sports",
    9: "Lifestyle",
    10: "Infotainment",
    12: "News",
    13: "Music",
    15: "Devotional",
    16: "Business",
    17: "Educational",
    18: "Shopping",
    19: "JioDarshan",
}

LANGUAGE_MAP = {
    0: "All Languages",
    1: "Hindi",
    2: "Marathi",
    3: "Punjabi",
    4: "Urdu",
    5: "Bengali",
    6: "English",
    7: "Malayalam",
    8: "Tamil",
    9: "Gujarati",
    10: "Odia",
    11: "Telugu",
    12: "Bhojpuri",
    13: "Kannada",
    14: "Assamese",
    15: "Nepali",
    16: "French",
    18: "Other",
}


class ChannelManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.data_dir = settings.data_dir
        self.channels_file = self.data_dir / "channels.json"
        self.epg_file = self.data_dir / "epg.xml.gz"
        self._channels_cache: List[Dict[str, Any]] = []

    def get_channels_cache(self) -> List[Dict[str, Any]]:
        if self._channels_cache:
            return self._channels_cache
        if self.channels_file.exists():
            try:
                data = json.loads(self.channels_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._channels_cache = data
                    return self._channels_cache
            except Exception as e:
                logger.error(f"Error loading channels from {self.channels_file}: {e}")
        return []

    async def sync_channels(self, force: bool = False) -> int:
        client_kwargs = {"timeout": 15.0}
        if self.settings.proxy_enabled and self.settings.proxy_url:
            client_kwargs["proxy"] = self.settings.proxy_url

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                headers = {
                    "User-Agent": "okhttp/4.9.3",
                    "Accept": "application/json",
                    "devicetype": "phone",
                    "os": "android",
                    "appkey": "NzNiMDhlYzQyNjJm",
                    "lbcookie": "1",
                    "usertype": "JIO",
                }
                resp = await client.get(MOBILE_CHANNELS_URL, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"Mobile channel list endpoint returned HTTP {resp.status_code}, falling back to CDN...")
                    resp = await client.get(CDN_DATA_URL, headers={"User-Agent": "okhttp/4.9.3"})

                if resp.status_code == 450:
                    raise RuntimeError("Jio CDN returned HTTP 450 block. Please enable Upstream Residential Proxy in Settings.")
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to fetch channel catalog: HTTP {resp.status_code}")

                raw = resp.json()
                raw_channels = raw.get("result", [])
                if not raw_channels and isinstance(raw, list):
                    raw_channels = raw

                normalized = []
                for ch in raw_channels:
                    c_id = ch.get("channel_id")
                    if not c_id:
                        continue
                    name = ch.get("channel_name", f"Channel {c_id}")
                    cat_id = ch.get("channelCategoryId", 0)
                    lang_id = ch.get("channelLanguageId", 0)
                    logo_url = ch.get("logoUrl", "")
                    if logo_url and not logo_url.startswith("http"):
                        logo_url = IMAGE_BASE_URL + logo_url
                    is_hd = bool(ch.get("isHD", False))

                    genre = CATEGORY_MAP.get(cat_id, "General")
                    language = LANGUAGE_MAP.get(lang_id, "Other")
                    business_type = (ch.get("business_type") or "free").strip().lower()
                    is_premium = (business_type == "premium")

                    normalized.append({
                        "channel_id": int(c_id),
                        "channel_name": name,
                        "language": language,
                        "genre": genre,
                        "logo": logo_url,
                        "is_hd": is_hd,
                        "business_type": business_type,
                        "is_premium": is_premium,
                    })

                normalized.sort(key=lambda x: (x["channel_name"]))
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self.channels_file.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
                self._channels_cache = normalized
                logger.info(f"Successfully synced {len(normalized)} channels to disk cache.")
                return len(normalized)

        except Exception as e:
            logger.warning(f"Catalog sync failed ({e}). Preserving existing offline disk cache.")
            cached = self.get_channels_cache()
            if cached:
                return len(cached)
            raise e

    def get_channels(
        self,
        lang: Optional[str] = None,
        genre: Optional[str] = None,
        search: Optional[str] = None,
        is_hd: Optional[bool] = None,
        working_only: bool = False,
    ) -> List[Dict[str, Any]]:
        channels = self.get_channels_cache()
        filtered = channels

        if working_only:
            filtered = [c for c in filtered if not c.get("is_premium", False)]

        if lang:
            langs = [item.strip().lower() for item in lang.split(",")]
            filtered = [c for c in filtered if c.get("language", "").lower() in langs]

        if genre:
            genres = [g.strip().lower() for g in genre.split(",")]
            filtered = [c for c in filtered if c.get("genre", "").lower() in genres]

        if is_hd is not None:
            filtered = [c for c in filtered if c.get("is_hd") == is_hd]

        if search:
            s = search.strip().lower()
            filtered = [c for c in filtered if s in c.get("channel_name", "").lower() or s in str(c.get("channel_id"))]

        return filtered

    def generate_m3u(
        self,
        base_url: str,
        lang: Optional[str] = None,
        genre: Optional[str] = None,
        is_hd: Optional[bool] = None,
        working_only: bool = False,
    ) -> str:
        base = base_url.rstrip("/")
        channels = self.get_channels(lang=lang, genre=genre, is_hd=is_hd, working_only=working_only)
        epg_url = f"{base}/epg.xml.gz"

        lines = [f'#EXTM3U x-tvg-url="{epg_url}"']

        for c in channels:
            cid = c["channel_id"]
            name = c["channel_name"]
            logo = c.get("logo", "")
            group = c.get("genre", "General")
            c_lang = c.get("language", "")
            stream_url = f"{base}/live/{cid}.m3u8"

            lines.append(
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}" tvg-language="{c_lang}", {name}'
            )
            lines.append(stream_url)

        return "\n".join(lines) + "\n"



    def get_epg_path(self) -> Path:
        if not self.epg_file.exists():
            self._generate_dummy_epg()
        return self.epg_file

    def _generate_dummy_epg(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        root = ET.Element("tv")
        channels = self.get_channels_cache()
        for ch in channels:
            c_elem = ET.SubElement(root, "channel", id=str(ch["channel_id"]))
            dn = ET.SubElement(c_elem, "display-name")
            dn.text = ch["channel_name"]
            if ch.get("logo"):
                ET.SubElement(c_elem, "icon", src=ch["logo"])
        raw_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with gzip.open(self.epg_file, "wb") as f:
            f.write(raw_xml)
