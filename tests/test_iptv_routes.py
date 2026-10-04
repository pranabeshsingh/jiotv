import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from pathlib import Path
import json
from app.main import create_app
from app.config import Settings

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
            "is_hd": False
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
