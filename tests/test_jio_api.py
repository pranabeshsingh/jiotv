import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings
from app.jio_api import JioApiClient


@pytest.fixture
def api_client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    return JioApiClient(settings=settings)

@pytest.mark.asyncio
async def test_send_otp_success(api_client: JioApiClient):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(
            204, headers={"content-type": "application/json"}
        )
        res = await api_client.send_otp("+919999999999")
        assert res["status"] == "success"
        assert mock_post.called

@pytest.mark.asyncio
async def test_verify_otp_success(api_client: JioApiClient, tmp_path: Path):
    mock_resp = {
        "ssoToken": "mock_sso_token_123",
        "authToken": "mock_auth_token_456",
        "sessionAttributes": {
            "user": {
                "subscriberId": "crm_999",
                "unique": "uid_888"
            }
        }
    }
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json=mock_resp)
        res = await api_client.verify_otp("+919999999999", "123456")
        assert res["status"] == "success"
        assert (tmp_path / "auth.json").exists()
        auth_data = json.loads((tmp_path / "auth.json").read_text())
        assert auth_data["ssoToken"] == "mock_sso_token_123"

@pytest.mark.asyncio
async def test_get_playback_url(api_client: JioApiClient, tmp_path: Path):
    # Seed auth.json
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({
        "ssoToken": "mock_sso",
        "accessToken": "mock_access",
        "crm": "mock_crm",
        "uniqueId": "mock_uid",
        "deviceId": "mock_device"
    }))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(
            200, json={"result": "https://jiotvbpkmob.cdn.jio.com/bpk-tv/202/Fallback/index.m3u8?token=xyz"}
        )
        url = await api_client.get_playback_url("202")
        assert "jiotvbpkmob.cdn.jio.com" in url


@pytest.mark.asyncio
async def test_has_premium_entitlement(api_client: JioApiClient, tmp_path: Path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({
        "ssoToken": "mock_sso",
        "accessToken": "mock_access",
        "crm": "mock_crm",
        "uniqueId": "mock_uid",
    }))

    # 1. Base plan only
    mock_base = {"PackageInfo": [{"planid": "1", "package_name": "jio", "business_type": "jio"}]}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=mock_base)
        has_prem = await api_client.has_premium_entitlement()
        assert has_prem is False

    # 2. Premium plan active
    mock_prem = {
        "PackageInfo": [
            {"planid": "1", "package_name": "jio", "business_type": "jio"},
            {"planid": "Rs55_30D_JioTV", "package_name": "JioTV Premium", "business_type": "premium"}
        ]
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=mock_prem)
        has_prem = await api_client.has_premium_entitlement(force=True)
        assert has_prem is True

