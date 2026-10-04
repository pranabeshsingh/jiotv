import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.channel_manager import ChannelManager
from app.config import Settings, get_settings
from app.jio_api import JioApiClient
from app.routes.api import router as api_router
from app.routes.iptv import router as iptv_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure channels are cached; if empty, attempt background sync
    channel_mgr: ChannelManager = app.state.channel_manager
    if not channel_mgr.get_channels_cache():
        try:
            await channel_mgr.sync_channels()
        except Exception as e:
            logger.warning(f"Startup channel sync failed: {e}. Waiting for user/proxy sync.")

    yield
    # Shutdown logic if any


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="JioTV IPTV Server",
        description="Lightweight self-hosted IPTV server for JioTV streaming to Kodi & IPTV clients",
        version="1.0.0",
        lifespan=lifespan,
    )

    # State
    app.state.settings = settings
    app.state.jio_client = JioApiClient(settings=settings)
    app.state.channel_manager = ChannelManager(settings=settings)

    # Static assets mount if directory exists
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routers
    app.include_router(iptv_router)
    app.include_router(api_router)

    return app


app = create_app()
