import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Any

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def parse_toml_fallback(text: str) -> Dict[str, Any]:
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            data[k] = v
    return data


def parse_toml_and_migrate(toml_path: Path, output_data_dir: Path) -> bool:
    if not toml_path.exists():
        print(f"Error: Source TOML file not found at {toml_path}", file=sys.stderr)
        return False

    output_data_dir.mkdir(parents=True, exist_ok=True)
    raw_content = toml_path.read_text(encoding="utf-8")

    data = {}
    if tomllib is not None:
        try:
            parsed = tomllib.loads(raw_content)
            data = parsed.get("data", parsed.get("auth", parsed))
        except Exception as e:
            print(f"Warning: tomllib failed ({e}), falling back to regex parser", file=sys.stderr)
            data = parse_toml_fallback(raw_content)
    else:
        data = parse_toml_fallback(raw_content)

    auth_json = {
        "accessToken": data.get("accessToken", ""),
        "ssoToken": data.get("ssoToken", ""),
        "refreshToken": data.get("refreshToken", ""),
        "crm": data.get("crm", ""),
        "uniqueId": data.get("uniqueId", ""),
        "deviceId": data.get("deviceId", ""),
        "lastTokenRefreshTime": data.get("lastTokenRefreshTime", ""),
        "subscriberName": data.get("name", "Jio Subscriber"),
    }

    auth_dest = output_data_dir / "auth.json"
    auth_dest.write_text(json.dumps(auth_json, indent=2), encoding="utf-8")
    print(f"✓ Successfully wrote auth credentials to {auth_dest}")

    # Migrate cached_channels.json if present
    source_dir = toml_path.parent
    source_channels = source_dir / "cached_channels.json"
    if source_channels.exists():
        try:
            raw_ch = json.loads(source_channels.read_text(encoding="utf-8"))
            items = raw_ch.get("result", raw_ch) if isinstance(raw_ch, dict) else raw_ch
            norm_list = []
            for ch in items:
                cid = ch.get("channel_id")
                if not cid:
                    continue
                logo = ch.get("logoUrl", "")
                if logo and not logo.startswith("http"):
                    logo = "https://jiotv.catchup.cdn.jio.com/dare_images/images/" + logo
                norm_list.append({
                    "channel_id": int(cid),
                    "channel_name": ch.get("channel_name", f"Channel {cid}"),
                    "language": "Hindi" if ch.get("channelLanguageId") == 1 else ("English" if ch.get("channelLanguageId") == 6 else "Other"),
                    "genre": "Entertainment" if ch.get("channelCategoryId") == 5 else "General",
                    "logo": logo,
                    "is_hd": bool(ch.get("isHD", False)),
                })
            dest_channels = output_data_dir / "channels.json"
            dest_channels.write_text(json.dumps(norm_list, indent=2), encoding="utf-8")
            print(f"✓ Migrated {len(norm_list)} cached channels to {dest_channels}")
        except Exception as e:
            print(f"Notice: Could not parse cached_channels.json: {e}", file=sys.stderr)

    # Migrate epg.xml.gz if present
    source_epg = source_dir / "epg.xml.gz"
    if source_epg.exists():
        try:
            shutil.copy2(source_epg, output_data_dir / "epg.xml.gz")
            print(f"✓ Migrated EPG file to {output_data_dir / 'epg.xml.gz'}")
        except Exception as e:
            print(f"Notice: Could not copy epg.xml.gz: {e}", file=sys.stderr)

    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 migrate_credentials.py <path_to_store_v4.toml> <output_data_dir>")
        sys.exit(1)

    toml_path = Path(sys.argv[1])
    data_dir = Path(sys.argv[2])
    success = parse_toml_and_migrate(toml_path, data_dir)
    sys.exit(0 if success else 1)
