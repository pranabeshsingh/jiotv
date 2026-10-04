from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return create_app(settings=settings)

@pytest.mark.asyncio
async def test_dashboard_renders_html(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "JioTV" in resp.text
        assert "Network & Proxy Settings" in resp.text
        assert "Client Setup" in resp.text
        assert "playlist.m3u" in resp.text
