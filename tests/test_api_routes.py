import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from app.main import create_app
from app.config import Settings

@pytest.fixture
def app(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return create_app(settings=settings)

@pytest.mark.asyncio
async def test_api_status(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "proxy_enabled" in data
        assert "channels_count" in data
        assert "jio_auth" in data

@pytest.mark.asyncio
async def test_update_proxy_settings_api(app, tmp_path: Path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"proxy_enabled": True, "proxy_url": "http://100.107.251.122:8888"}
        resp = await client.post("/api/settings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["proxy_enabled"] is True
        assert data["proxy_url"] == "http://100.107.251.122:8888"
        
        # Verify persistence and updated status
        status_resp = await client.get("/api/status")
        assert status_resp.json()["proxy_enabled"] is True
        assert status_resp.json()["proxy_url"] == "http://100.107.251.122:8888"
