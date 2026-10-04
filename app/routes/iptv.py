import logging
import re
import urllib.parse
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from app.channel_manager import ChannelManager
from app.config import Settings
from app.jio_api import JioApiClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IPTV"])


def get_base_url(request: Request, settings: Settings) -> str:
    if settings.base_url:
        return settings.base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def rewrite_m3u8(content: str, parent_url: str, base_url: str, channel_id: str) -> str:
    parent_no_q = parent_url.split("?")[0]
    cdn_base = parent_no_q.rsplit("/", 1)[0]
    query = parent_url.split("?")[1] if "?" in parent_url else ""

    lines = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-KEY:"):
            m = re.search(r'URI="([^"]+)"', line)
            if m:
                raw_key_uri = m.group(1)
                if not raw_key_uri.startswith("http"):
                    raw_key_uri = f"{cdn_base}/{raw_key_uri}"
                if query and "?" not in raw_key_uri:
                    raw_key_uri = f"{raw_key_uri}?{query}"
                encoded_key_uri = urllib.parse.quote(raw_key_uri, safe="")
                new_key_uri = f"{base_url}/render.key?url={encoded_key_uri}&cid={channel_id}"
                line = line[: m.start(1)] + new_key_uri + line[m.end(1) :]
            lines.append(line)
        elif line.startswith("#"):
            m = re.search(r'URI="([^"]+)"', line)
            if m and (line.endswith('.m3u8"') or ".m3u8?" in line):
                sub_uri = m.group(1)
                if not sub_uri.startswith("http"):
                    sub_uri = f"{cdn_base}/{sub_uri}"
                if query and "?" not in sub_uri:
                    sub_uri = f"{sub_uri}?{query}"
                encoded_sub = urllib.parse.quote(sub_uri, safe="")
                new_sub_uri = f"{base_url}/render.m3u8?url={encoded_sub}&cid={channel_id}"
                line = line[: m.start(1)] + new_sub_uri + line[m.end(1) :]
            lines.append(line)
        else:
            if line.endswith(".m3u8") or ".m3u8?" in line:
                sub_url = line if line.startswith("http") else f"{cdn_base}/{line}"
                if query and "?" not in sub_url:
                    sub_url = f"{sub_url}?{query}"
                encoded_sub = urllib.parse.quote(sub_url, safe="")
                lines.append(f"{base_url}/render.m3u8?url={encoded_sub}&cid={channel_id}")
            elif (
                line.endswith(".ts")
                or line.endswith(".aac")
                or ".ts?" in line
                or ".aac?" in line
            ):
                seg_url = line if line.startswith("http") else f"{cdn_base}/{line}"
                if query and "?" not in seg_url:
                    seg_url = f"{seg_url}?{query}"
                lines.append(seg_url)
            else:
                lines.append(line)
    return "\n".join(lines) + "\n"


@router.get("/playlist.m3u", response_class=PlainTextResponse)
async def get_playlist(
    request: Request,
    lang: Optional[str] = Query(None, description="Comma-separated language filter (e.g. Hindi,English)"),
    genre: Optional[str] = Query(None, description="Comma-separated genre filter (e.g. Entertainment,News)"),
    is_hd: Optional[bool] = Query(None, description="Filter for HD channels"),
    filter: Optional[str] = Query(None, description="Filter channels, e.g. 'working', 'free', 'subscribed'"),
    working: Optional[bool] = Query(None, description="Set to true to only include working/unlocked channels"),
):
    settings: Settings = request.app.state.settings
    channel_mgr: ChannelManager = request.app.state.channel_manager
    base_url = get_base_url(request, settings)

    working_only = False
    if working:
        working_only = True
    elif filter and filter.strip().lower() in ("working", "free", "subscribed"):
        working_only = True

    jio_client: JioApiClient = request.app.state.jio_client
    has_premium = await jio_client.has_premium_entitlement()
    effective_working_only = working_only and not has_premium

    m3u_content = channel_mgr.generate_m3u(
        base_url=base_url,
        lang=lang,
        genre=genre,
        is_hd=is_hd,
        working_only=effective_working_only,
    )
    return PlainTextResponse(
        content=m3u_content,
        media_type="application/vnd.apple.mpegurl",
        headers={"Content-Disposition": 'inline; filename="playlist.m3u"'},
    )


@router.get("/playlist_working.m3u", response_class=PlainTextResponse)
@router.get("/working.m3u", response_class=PlainTextResponse)
async def get_working_playlist(
    request: Request,
    lang: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    is_hd: Optional[bool] = Query(None),
):
    settings: Settings = request.app.state.settings
    channel_mgr: ChannelManager = request.app.state.channel_manager
    jio_client: JioApiClient = request.app.state.jio_client
    base_url = get_base_url(request, settings)

    has_premium = await jio_client.has_premium_entitlement()
    effective_working_only = not has_premium

    m3u_content = channel_mgr.generate_m3u(
        base_url=base_url,
        lang=lang,
        genre=genre,
        is_hd=is_hd,
        working_only=effective_working_only,
    )
    return PlainTextResponse(
        content=m3u_content,
        media_type="application/vnd.apple.mpegurl",
        headers={"Content-Disposition": 'inline; filename="playlist_working.m3u"'},
    )


@router.get("/epg.xml.gz")
async def get_epg(request: Request):
    channel_mgr: ChannelManager = request.app.state.channel_manager
    epg_path = channel_mgr.get_epg_path()
    if not epg_path.exists():
        raise HTTPException(status_code=404, detail="EPG not available")
    return FileResponse(
        path=epg_path,
        media_type="application/gzip",
        filename="epg.xml.gz",
        headers={"Content-Disposition": 'attachment; filename="epg.xml.gz"'},
    )


@router.get("/live/{channel_id}")
@router.get("/live/{channel_id}.m3u8")
async def get_live_stream(channel_id: str, request: Request):
    clean_id = channel_id.removesuffix(".m3u8")
    jio_client: JioApiClient = request.app.state.jio_client
    settings: Settings = request.app.state.settings
    base_url = get_base_url(request, settings)
    try:
        playback_url = await jio_client.get_playback_url(clean_id)
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(playback_url)
                if resp.status_code == 200 and ("#EXTM3U" in resp.text):
                    rewritten = rewrite_m3u8(resp.text, str(resp.url), base_url, clean_id)
                    return Response(
                        content=rewritten,
                        media_type="application/vnd.apple.mpegurl",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                    )
        except Exception as e:
            logger.warning(f"Could not rewrite upstream playlist for channel {clean_id}: {e}")
        return RedirectResponse(url=playback_url, status_code=302)
    except Exception as e:
        logger.error(f"Failed to resolve playback URL for channel {clean_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Playback resolution failed: {str(e)}")


@router.get("/render.m3u8")
async def render_m3u8(url: str, cid: str, request: Request):
    settings: Settings = request.app.state.settings
    base_url = get_base_url(request, settings)
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="Upstream playlist error")
            rewritten = rewrite_m3u8(resp.text, str(resp.url), base_url, cid)
            return Response(
                content=rewritten,
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to render sub-playlist for channel {cid}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to render playlist: {str(e)}")


@router.get("/render.key")
async def render_key(url: str, cid: str, request: Request):
    jio_client: JioApiClient = request.app.state.jio_client
    try:
        key_bytes = await jio_client.get_stream_key(url, cid)
        return Response(
            content=key_bytes,
            media_type="application/octet-stream",
            headers={"Cache-Control": "max-age=60"},
        )
    except Exception as e:
        logger.error(f"Failed to fetch key for channel {cid}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch decryption key: {str(e)}")

