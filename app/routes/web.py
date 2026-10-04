from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.channel_manager import ChannelManager
from app.config import Settings
from app.jio_api import JioApiClient

templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter(tags=["WebUI"])


def is_authenticated(request: Request, settings: Settings) -> bool:
    if not settings.dashboard_password:
        return True
    session_cookie = request.cookies.get("auth_session")
    return session_cookie == f"logged_in_{settings.dashboard_password}"


@router.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    settings: Settings = request.app.state.settings
    if not is_authenticated(request, settings):
        return RedirectResponse(url="/login", status_code=303)

    channel_mgr: ChannelManager = request.app.state.channel_manager
    jio_client: JioApiClient = request.app.state.jio_client

    channels = channel_mgr.get_channels_cache()
    auth_state = jio_client.get_auth_state()

    base_url = settings.base_url.rstrip("/") if settings.base_url else str(request.base_url).rstrip("/")

    context = {
        "subscriber_name": auth_state.get("subscriber_name", "Not logged in"),
        "mobile": auth_state.get("mobile", ""),
        "channels_count": len(channels),
        "proxy_enabled": settings.proxy_enabled,
        "proxy_url": settings.proxy_url,
        "base_url": base_url,
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=context,
    )


@router.get("/login", response_class=HTMLResponse)
async def login_view(request: Request):
    settings: Settings = request.app.state.settings
    if is_authenticated(request, settings):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...)):
    settings: Settings = request.app.state.settings
    if password == settings.dashboard_password:
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(
            key="auth_session",
            value=f"logged_in_{settings.dashboard_password}",
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30, # 30 days
        )
        return resp
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Incorrect password. Please try again."},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("auth_session")
    return resp
