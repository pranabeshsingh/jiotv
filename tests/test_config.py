import json
from pathlib import Path

from app.config import Settings, load_settings, save_runtime_settings


def test_settings_defaults(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    assert settings.proxy_enabled is False
    assert settings.proxy_url == ""
    assert settings.port == 5001

def test_runtime_settings_override(tmp_path: Path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "proxy_enabled": True,
        "proxy_url": "http://100.107.251.122:8888"
    }))

    settings = load_settings(data_dir=tmp_path)
    assert settings.proxy_enabled is True
    assert settings.proxy_url == "http://100.107.251.122:8888"

def test_save_runtime_settings(tmp_path: Path):
    save_runtime_settings(tmp_path, proxy_enabled=True, proxy_url="http://1.2.3.4:8080")
    settings = load_settings(data_dir=tmp_path)
    assert settings.proxy_enabled is True
    assert settings.proxy_url == "http://1.2.3.4:8080"
