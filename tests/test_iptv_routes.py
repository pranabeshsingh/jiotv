import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app(tmp_path: Path):
    channels_file = tmp_path / "channels.json"
    channels_file.write_text(json.dumps([
        {
            "channel_id": 202,
            "channel_name": "DD National",
            "language": "Hindi",
            "genre": "Entertainment",
            "logo": "http://example.com/logo.png",
            "is_hd": False,
            "business_type": "free",
            "is_premium": False,
        },
        {
            "channel_id": 154,
            "channel_name": "Sony SAB",
            "language": "Hindi",
            "genre": "Entertainment",
            "logo": "http://example.com/sab.png",
            "is_hd": False,
            "business_type": "premium",
            "is_premium": True,
        }
    ]))
    epg_file = tmp_path / "epg.xml.gz"
    epg_file.write_bytes(b"dummy_epg_data")

    settings = Settings(data_dir=tmp_path, base_url="https://tv.trylocalhost.com")
    return create_app(settings=settings)


@pytest.mark.asyncio
async def test_playlist_m3u(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://tv.trylocalhost.com") as client:
        resp = await client.get("/playlist.m3u")
        assert resp.status_code == 200
        assert "#EXTM3U" in resp.text
        assert "DD National" in resp.text
        assert "/live/202" in resp.text

@pytest.mark.asyncio
async def test_epg_xml_gz(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://tv.trylocalhost.com") as client:
        resp = await client.get("/epg.xml.gz")
        assert resp.status_code == 200
        assert resp.headers["content-type"] in ("application/gzip", "application/x-gzip", "application/octet-stream")
        assert resp.content == b"dummy_epg_data"

@pytest.mark.asyncio
async def test_live_stream_redirect(app):
    transport = ASGITransport(app=app)
    with patch("app.jio_api.JioApiClient.get_playback_url", new_callable=AsyncMock) as mock_playback:
        mock_playback.return_value = "https://live.cdn.jio.com/stream.m3u8?token=xyz"
        async with AsyncClient(transport=transport, base_url="https://tv.trylocalhost.com", follow_redirects=False) as client:
            resp = await client.get("/live/202")
            assert resp.status_code == 302
            assert resp.headers["Location"] == "https://live.cdn.jio.com/stream.m3u8?token=xyz"


@pytest.mark.asyncio
async def test_playlist_working_endpoints(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://tv.trylocalhost.com") as client:
        # Default has all channels
        resp_all = await client.get("/playlist.m3u")
        assert "DD National" in resp_all.text
        assert "Sony SAB" in resp_all.text

        # Filter working via query param
        resp_q = await client.get("/playlist.m3u?filter=working")
        assert resp_q.status_code == 200
        assert "DD National" in resp_q.text
        assert "Sony SAB" not in resp_q.text

        # Dedicated endpoint /playlist_working.m3u
        resp_working = await client.get("/playlist_working.m3u")
        assert resp_working.status_code == 200
        assert "DD National" in resp_working.text
        assert "Sony SAB" not in resp_working.text

        # API channels filter
        resp_api = await client.get("/api/channels?filter=working")
        assert resp_api.status_code == 200
        data = resp_api.json()
        assert data["total"] == 1
        assert data["channels"][0]["channel_name"] == "DD National"

