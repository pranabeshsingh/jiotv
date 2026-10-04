import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.channel_manager import ChannelManager
from app.config import Settings, save_runtime_settings
from app.jio_api import JioApiClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Management API"])


class SettingsUpdate(BaseModel):
    proxy_enabled: Optional[bool] = None
    proxy_url: Optional[str] = None
    base_url: Optional[str] = None


class SendOTPRequest(BaseModel):
    mobile: str


class VerifyOTPRequest(BaseModel):
    mobile: str
    otp: str


@router.get("/status")
async def get_status(request: Request) -> Dict[str, Any]:
    settings: Settings = request.app.state.settings
    channel_mgr: ChannelManager = request.app.state.channel_manager
    jio_client: JioApiClient = request.app.state.jio_client

    channels = channel_mgr.get_channels_cache()
    auth_state = jio_client.get_auth_state()

    return {
        "status": "online",
        "channels_count": len(channels),
        "proxy_enabled": settings.proxy_enabled,
        "proxy_url": settings.proxy_url,
        "base_url": settings.base_url,
        "jio_auth": auth_state,
    }


@router.get("/settings")
async def get_settings_endpoint(request: Request) -> Dict[str, Any]:
    settings: Settings = request.app.state.settings
    return {
        "proxy_enabled": settings.proxy_enabled,
        "proxy_url": settings.proxy_url,
        "base_url": settings.base_url,
    }


@router.post("/settings")
async def update_settings_endpoint(
    payload: SettingsUpdate, request: Request
) -> Dict[str, Any]:
    current_settings: Settings = request.app.state.settings
    new_settings = save_runtime_settings(
        data_dir=current_settings.data_dir,
        proxy_enabled=payload.proxy_enabled,
        proxy_url=payload.proxy_url,
        base_url=payload.base_url,
    )
    # Update running state
    request.app.state.settings = new_settings
    request.app.state.jio_client = JioApiClient(settings=new_settings)
    request.app.state.channel_manager = ChannelManager(settings=new_settings)

    return {
        "status": "success",
        "proxy_enabled": new_settings.proxy_enabled,
        "proxy_url": new_settings.proxy_url,
        "base_url": new_settings.base_url,
    }


@router.post("/test-connectivity")
async def test_connectivity_endpoint(
    request: Request,
    payload: Optional[SettingsUpdate] = None,
) -> Dict[str, Any]:
    settings: Settings = request.app.state.settings
    jio_client: JioApiClient = request.app.state.jio_client

    proxy_to_test = None
    if payload and payload.proxy_url:
        proxy_to_test = payload.proxy_url
    elif settings.proxy_enabled and settings.proxy_url:
        proxy_to_test = settings.proxy_url

    results = await jio_client.test_connectivity(proxy_url=proxy_to_test)
    return results


@router.post("/auth/otp/send")
async def send_otp_endpoint(payload: SendOTPRequest, request: Request):
    jio_client: JioApiClient = request.app.state.jio_client
    try:
        res = await jio_client.send_otp(payload.mobile)
        return res
    except Exception as e:
        logger.error(f"OTP send error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/otp/verify")
async def verify_otp_endpoint(payload: VerifyOTPRequest, request: Request):
    jio_client: JioApiClient = request.app.state.jio_client
    try:
        res = await jio_client.verify_otp(payload.mobile, payload.otp)
        return res
    except Exception as e:
        logger.error(f"OTP verify error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync")
async def trigger_sync(request: Request):
    channel_mgr: ChannelManager = request.app.state.channel_manager
    try:
        count = await channel_mgr.sync_channels(force=True)
        return {"status": "success", "channels_synced": count}
    except Exception as e:
        logger.error(f"Manual sync failed: {e}")
        raise HTTPException(status_code=502, detail=f"Sync failed: {str(e)}")


@router.get("/channels")
async def list_channels(
    request: Request,
    lang: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_hd: Optional[bool] = Query(None),
    filter: Optional[str] = Query(None),
    working: Optional[bool] = Query(None),
):
    channel_mgr: ChannelManager = request.app.state.channel_manager
    jio_client: JioApiClient = request.app.state.jio_client

    working_only = False
    if working:
        working_only = True
    elif filter and filter.strip().lower() in ("working", "free", "subscribed"):
        working_only = True

    has_premium = await jio_client.has_premium_entitlement()
    effective_working_only = working_only and not has_premium

    channels = channel_mgr.get_channels(
        lang=lang,
        genre=genre,
        search=search,
        is_hd=is_hd,
        working_only=effective_working_only,
    )
    return {"total": len(channels), "channels": channels}


