from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channel_manager import ChannelManager
from app.config import Settings


@pytest.fixture
def channel_mgr(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return ChannelManager(settings=settings)

@pytest.mark.asyncio
async def test_sync_channels_and_generate_m3u(channel_mgr: ChannelManager, tmp_path: Path):
    mock_catalog = {
        "result": [
            {
                "channel_id": 202,
                "channel_name": "DD National",
                "channelLanguageId": 1,  # Hindi
                "channelCategoryId": 5,  # Entertainment
                "logoUrl": "dd_national.png",
                "isHD": False
            },
            {
                "channel_id": 173,
                "channel_name": "Aaj Tak",
                "channelLanguageId": 1,  # Hindi
                "channelCategoryId": 12, # News
                "logoUrl": "aaj_tak.png",
                "isHD": True
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=mock_catalog)
        count = await channel_mgr.sync_channels()
        assert count == 2

        # Verify cached file
        assert (tmp_path / "channels.json").exists()

        # Verify M3U generation
        m3u = channel_mgr.generate_m3u(base_url="https://tv.trylocalhost.com")
        assert "#EXTM3U" in m3u
        assert "DD National" in m3u
        assert "https://tv.trylocalhost.com/live/202" in m3u
        assert 'group-title="Entertainment"' in m3u
        assert 'tvg-id="202"' in m3u

def test_filter_channels(channel_mgr: ChannelManager, tmp_path: Path):
    # Pre-populate channels.json
    data = [
        {"channel_id": 202, "channel_name": "DD National", "language": "Hindi", "genre": "Entertainment", "is_hd": False},
        {"channel_id": 173, "channel_name": "Aaj Tak", "language": "Hindi", "genre": "News", "is_hd": True},
        {"channel_id": 100, "channel_name": "BBC News", "language": "English", "genre": "News", "is_hd": True},
    ]
    import json
    (tmp_path / "channels.json").write_text(json.dumps(data))

    # Filter by genre
    news = channel_mgr.get_channels(genre="News")
    assert len(news) == 2
    assert all(c["genre"] == "News" for c in news)

    # Filter by language
    english = channel_mgr.get_channels(lang="English")
    assert len(english) == 1
    assert english[0]["channel_name"] == "BBC News"


def test_channel_manager_working_filter(channel_mgr: ChannelManager):
    channel_mgr._channels_cache = [
        {"channel_id": 154, "channel_name": "Sony SAB", "business_type": "premium", "is_premium": True},
        {"channel_id": 474, "channel_name": "Sony Pal", "business_type": "free", "is_premium": False},
        {"channel_id": 173, "channel_name": "Aaj Tak", "business_type": "free", "is_premium": False},
        {"channel_id": 100, "channel_name": "Jio Cinema", "business_type": "jio", "is_premium": False},
    ]
    all_channels = channel_mgr.get_channels(working_only=False)
    assert len(all_channels) == 4

    working_channels = channel_mgr.get_channels(working_only=True)
    assert len(working_channels) == 3
    assert not any(c["channel_name"] == "Sony SAB" for c in working_channels)

    # Test in generate_m3u
    m3u_working = channel_mgr.generate_m3u(base_url="https://tv.trylocalhost.com", working_only=True)
    assert "Sony Pal" in m3u_working
    assert "Sony SAB" not in m3u_working

