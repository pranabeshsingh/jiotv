import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
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
async def get_live_stream(channel_id: str, request: Request):
    jio_client: JioApiClient = request.app.state.jio_client
    try:
        playback_url = await jio_client.get_playback_url(channel_id)
        return RedirectResponse(url=playback_url, status_code=302)
    except Exception as e:
        logger.error(f"Failed to resolve playback URL for channel {channel_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Playback resolution failed: {str(e)}")
