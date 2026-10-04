import base64
import datetime
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

JIOTV_API_DOMAIN = "jiotvapi.media.jio.com"
AUTH_MEDIA_DOMAIN = "auth.media.jio.com"
CDN_DATA_DOMAIN = "jiotv.data.cdn.jio.com"

APPKEY = "NzNiMDhlYzQyNjJm"
USERGROUP = "tvYR7NSNn7rymo3F"
VERSION_CODE = "422"
OS_NAME = "android"
DEVICE_TYPE = "phone"
USER_AGENT = "okhttp/4.9.3"


class JioApiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.data_dir = settings.data_dir
        self.auth_file = self.data_dir / "auth.json"
        self._ensure_device_id()

    def _ensure_device_id(self) -> str:
        device_id_file = self.data_dir / "device_id.txt"
        if device_id_file.exists():
            return device_id_file.read_text().strip()
        new_id = uuid.uuid4().hex[:16]
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            device_id_file.write_text(new_id)
        except Exception:
            pass
        return new_id

    @property
    def device_id(self) -> str:
        return self._ensure_device_id()

    def load_auth_data(self) -> Dict[str, Any]:
        if not self.auth_file.exists():
            return {}
        try:
            return json.loads(self.auth_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read auth.json: {e}")
            return {}

    def save_auth_data(self, data: Dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.auth_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_auth_state(self) -> Dict[str, Any]:
        auth = self.load_auth_data()
        sso_token = auth.get("ssoToken") or auth.get("sso_token")
        logged_in = bool(sso_token)
        subscriber_name = auth.get("subscriberName") or auth.get("name") or "Jio Subscriber"
        mobile = auth.get("mobile", "")
        last_refresh = auth.get("lastTokenRefreshTime", "")
        entitlements_file = self.data_dir / "entitlements.json"
        has_premium = False
        plan_desc = "Standard Jio Mobile"
        if entitlements_file.exists():
            try:
                data = json.loads(entitlements_file.read_text(encoding="utf-8"))
                pkgs = data.get("PackageInfo", [])
                if len(pkgs) > 1:
                    has_premium = True
                    plan_desc = "JioTV Premium Active"
                else:
                    for pkg in pkgs:
                        b_type = str(pkg.get("business_type", "")).lower()
                        p_name = str(pkg.get("package_name", "")).lower()
                        p_id = str(pkg.get("planid", "")).lower()
                        p_type = str(pkg.get("plantype", "")).lower()
                        if b_type == "premium" or "premium" in p_name or "rs55" in p_id or p_type == "ott" or (p_id and p_id != "1"):
                            has_premium = True
                            plan_desc = "JioTV Premium Active"
                            break
            except Exception:
                pass

        return {
            "logged_in": logged_in,
            "subscriber_name": subscriber_name,
            "mobile": mobile,
            "has_access_token": bool(auth.get("accessToken") or auth.get("access_token")),
            "last_refresh": last_refresh,
            "device_id": self.device_id,
            "has_premium": has_premium,
            "plan_desc": plan_desc,
        }

    async def get_entitlements(self, force: bool = False) -> Dict[str, Any]:
        entitlements_file = self.data_dir / "entitlements.json"
        if not force and entitlements_file.exists():
            try:
                return json.loads(entitlements_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        auth = self.load_auth_data()
        access_token = auth.get("accessToken") or auth.get("access_token", "")
        if not access_token:
            return {}

        url = f"https://{JIOTV_API_DOMAIN}/userservice/apis/v1/plans"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "devicetype": DEVICE_TYPE,
            "os": OS_NAME,
            "versionCode": VERSION_CODE,
            "accesstoken": access_token,
            "uniqueId": auth.get("uniqueId") or auth.get("unique_id", ""),
        }
        client_kwargs = {"timeout": 10.0}
        if self.settings.proxy_enabled and self.settings.proxy_url:
            client_kwargs["proxy"] = self.settings.proxy_url

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    self.data_dir.mkdir(parents=True, exist_ok=True)
                    entitlements_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    return data
        except Exception as e:
            logger.warning(f"Failed to fetch user entitlements: {e}")
        return {}

    async def has_premium_entitlement(self, force: bool = False) -> bool:
        data = await self.get_entitlements(force=force)
        pkg_info = data.get("PackageInfo", [])
        if len(pkg_info) > 1:
            return True
        for pkg in pkg_info:
            b_type = str(pkg.get("business_type", "")).lower()
            p_name = str(pkg.get("package_name", "")).lower()
            p_id = str(pkg.get("planid", "")).lower()
            p_type = str(pkg.get("plantype", "")).lower()
            if b_type == "premium" or "premium" in p_name or "rs55" in p_id or p_type == "ott" or (p_id and p_id != "1"):
                return True
        return False



    async def send_otp(self, mobile: str) -> Dict[str, Any]:
        cleaned = mobile.strip().replace(" ", "").replace("-", "")
        if not cleaned.startswith("+"):
            cleaned = "+91" + cleaned[-10:]
        encoded_number = base64.b64encode(cleaned.encode()).decode()

        url = f"https://{JIOTV_API_DOMAIN}/userservice/apis/v1/loginotp/send"
        headers = {
            "appname": "RJIL_JioTV",
            "os": OS_NAME,
            "devicetype": DEVICE_TYPE,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        payload = {"number": encoded_number}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 204):
                return {"status": "success", "message": "OTP sent successfully to " + cleaned}
            error_msg = resp.text
            try:
                err_json = resp.json()
                error_msg = err_json.get("message", error_msg)
            except Exception:
                pass
            raise RuntimeError(f"Jio OTP send failed ({resp.status_code}): {error_msg}")

    async def verify_otp(self, mobile: str, otp: str) -> Dict[str, Any]:
        cleaned = mobile.strip().replace(" ", "").replace("-", "")
        if not cleaned.startswith("+"):
            cleaned = "+91" + cleaned[-10:]
        encoded_number = base64.b64encode(cleaned.encode()).decode()

        url = f"https://{JIOTV_API_DOMAIN}/userservice/apis/v1/loginotp/verify"
        headers = {
            "appname": "RJIL_JioTV",
            "os": OS_NAME,
            "devicetype": DEVICE_TYPE,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        payload = {
            "number": encoded_number,
            "otp": otp.strip(),
            "deviceInfo": {
                "consumptionDeviceName": "SM-G930F",
                "info": {
                    "type": "android",
                    "platform": {"name": "SM-G930F"},
                    "androidId": self.device_id,
                },
            },
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"OTP verification failed ({resp.status_code}): {resp.text}")
            body = resp.json()

        sso_token = body.get("ssoToken", "")
        access_token = body.get("authToken", "")
        session_attr = body.get("sessionAttributes", {})
        user_info = session_attr.get("user", {})
        crm = user_info.get("subscriberId", "")
        unique_id = user_info.get("unique", "")
        name = user_info.get("name", "Jio Subscriber")
        refresh_token = body.get("refreshToken", "")

        auth_record = {
            "mobile": cleaned,
            "ssoToken": sso_token,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "crm": crm,
            "uniqueId": unique_id,
            "deviceId": self.device_id,
            "subscriberName": name,
            "lastTokenRefreshTime": str(int(time.time())),
        }
        self.save_auth_data(auth_record)
        return {"status": "success", "subscriber_name": name, "mobile": cleaned}

    async def refresh_token(self) -> bool:
        auth = self.load_auth_data()
        refresh_token = auth.get("refreshToken")
        access_token = auth.get("accessToken") or auth.get("access_token")
        if not refresh_token:
            logger.warning("No refresh token available in auth.json")
            return False

        url = f"https://{AUTH_MEDIA_DOMAIN}/tokenservice/apis/v1/refreshtoken?langId=6"
        headers = {
            "devicetype": DEVICE_TYPE,
            "versionCode": VERSION_CODE,
            "os": OS_NAME,
            "Content-Type": "application/json; charset=utf-8",
            "Host": AUTH_MEDIA_DOMAIN,
            "User-Agent": USER_AGENT,
            "accesstoken": access_token or "",
        }
        payload = {
            "appName": "RJIL_JioTV",
            "deviceId": auth.get("deviceId", self.device_id),
            "refreshToken": refresh_token,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(f"Token refresh failed: {resp.status_code} - {resp.text}")
                return False
            data = resp.json()
            new_access_token = data.get("authToken") or data.get("accessToken")
            if new_access_token:
                auth["accessToken"] = new_access_token
                auth["lastTokenRefreshTime"] = str(int(time.time()))
                self.save_auth_data(auth)
                logger.info("Successfully refreshed Jio access token")
                return True
        return False

    async def get_playback_url(self, channel_id: str) -> str:
        auth = self.load_auth_data()
        sso_token = auth.get("ssoToken") or auth.get("sso_token", "")
        access_token = auth.get("accessToken") or auth.get("access_token", "")
        crm = auth.get("crm", "")
        unique_id = auth.get("uniqueId") or auth.get("unique_id", "")
        device_id = auth.get("deviceId") or self.device_id

        if not sso_token:
            raise RuntimeError("Not authenticated with JioTV. Please log in first.")

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        begin_str = now_utc.strftime("%Y%m%dT%H%M%S")
        srno_str = now_utc.strftime("%Y%m%d")

        url = f"https://{JIOTV_API_DOMAIN}/playback/apis/v1.1/geturl?langId=6"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "appkey": APPKEY,
            "channel_id": str(channel_id),
            "crmid": crm,
            "userId": crm,
            "deviceId": device_id,
            "devicetype": DEVICE_TYPE,
            "isott": "false",
            "languageId": "6",
            "lbcookie": "1",
            "os": OS_NAME,
            "osVersion": "13",
            "subscriberId": crm,
            "uniqueId": unique_id,
            "User-Agent": USER_AGENT,
            "usergroup": USERGROUP,
            "versionCode": VERSION_CODE,
            "accesstoken": access_token,
            "ssotoken": sso_token,
        }

        form_data = {
            "channel_id": str(channel_id),
            "stream_type": "Seek",
            "begin": begin_str,
            "srno": srno_str,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, data=form_data, headers=headers)
            if resp.status_code == 401 or resp.status_code == 419:
                refreshed = await self.refresh_token()
                if refreshed:
                    return await self.get_playback_url(channel_id)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Jio playback error ({resp.status_code}): {resp.text}"
                )
            body = resp.json()
            result_url = body.get("result", "")
            if not result_url:
                raise RuntimeError(f"Playback API returned empty result: {body}")
            return result_url

    async def test_connectivity(self, proxy_url: Optional[str] = None) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "direct_playback": {"reachable": False, "status": 0, "latency_ms": 0, "error": None},
            "cdn": {"reachable": False, "status": 0, "latency_ms": 0, "proxied": bool(proxy_url), "error": None},
        }

        # 1. Test Playback API (Direct)
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(f"https://{JIOTV_API_DOMAIN}/playback/apis/v1.1/geturl")
                latency = int((time.time() - t0) * 1000)
                results["direct_playback"] = {
                    "reachable": True,
                    "status": resp.status_code,
                    "latency_ms": latency,
                    "error": None,
                }
        except Exception as e:
            results["direct_playback"]["error"] = str(e)

        # 2. Test CDN data endpoint (Direct vs Proxy)
        cdn_url = f"https://{CDN_DATA_DOMAIN}/apis/v1.4/getallchannel.php"
        t0 = time.time()
        try:
            client_kwargs = {"timeout": 8.0}
            if proxy_url:
                client_kwargs["proxy"] = proxy_url

            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.head(cdn_url)
                latency = int((time.time() - t0) * 1000)
                # Fastly returns 450 if blocked, 200/405/etc if reached
                results["cdn"] = {
                    "reachable": resp.status_code != 450,
                    "status": resp.status_code,
                    "latency_ms": latency,
                    "proxied": bool(proxy_url),
                    "error": "HTTP 450 Fastly CDN Block (Residential Proxy required)" if resp.status_code == 450 else None,
                }
        except Exception as e:
            results["cdn"]["error"] = str(e)

        return results
