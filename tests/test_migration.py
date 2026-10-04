import json
from pathlib import Path
from scripts.migrate_credentials import parse_toml_and_migrate

def test_parse_store_toml(tmp_path: Path):
    toml_content = """
    [data]
    accessToken = "test_access_token_123"
    ssoToken = "test_sso_token_456"
    refreshToken = "test_refresh_token_789"
    crm = "test_crm_111"
    uniqueId = "test_uid_222"
    deviceId = "test_dev_333"
    lastTokenRefreshTime = "1728000000"
    """
    toml_path = tmp_path / "store_v4.toml"
    toml_path.write_text(toml_content)
    
    out_dir = tmp_path / "data"
    success = parse_toml_and_migrate(toml_path, out_dir)
    assert success is True
    
    auth_data = json.loads((out_dir / "auth.json").read_text())
    assert auth_data["ssoToken"] == "test_sso_token_456"
    assert auth_data["accessToken"] == "test_access_token_123"
    assert auth_data["crm"] == "test_crm_111"
    assert auth_data["uniqueId"] == "test_uid_222"
