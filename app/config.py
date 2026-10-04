import json
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 5001
    base_url: str = "https://tv.trylocalhost.com"
    dashboard_password: str = ""
    secret_key: str = "jiotv-default-secret-key-change-me"
    data_dir: Path = Path("./data")
    proxy_enabled: bool = False
    proxy_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

def load_settings(data_dir: Optional[Path] = None) -> Settings:
    settings = Settings()
    if data_dir is not None:
        settings.data_dir = data_dir
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = settings.data_dir / "settings.json"
    if runtime_file.exists():
        try:
            overrides = json.loads(runtime_file.read_text(encoding="utf-8"))
            for key, val in overrides.items():
                if hasattr(settings, key) and val is not None:
                    setattr(settings, key, val)
        except Exception:
            pass
    return settings

def save_runtime_settings(data_dir: Path, **kwargs) -> Settings:
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = data_dir / "settings.json"
    current = {}
    if runtime_file.exists():
        try:
            current = json.loads(runtime_file.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current.update({k: v for k, v in kwargs.items() if v is not None})
    runtime_file.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return load_settings(data_dir=data_dir)

_current_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _current_settings
    if _current_settings is None:
        _current_settings = load_settings()
    return _current_settings

def refresh_settings() -> Settings:
    global _current_settings
    _current_settings = load_settings()
    return _current_settings
