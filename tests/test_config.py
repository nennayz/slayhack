import pytest
from config import Config, MissingAPIKeyError


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_ROBIN_MODEL", "gpt-robin")
    monkeypatch.setenv("OPENAI_AGENT_MODEL", "gpt-agent")
    monkeypatch.setenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", "drive-folder")
    cfg = Config.from_env()
    assert cfg.brave_search_api_key == "brave-key"
    assert cfg.openai_api_key == "openai-key"
    assert cfg.openai_robin_model == "gpt-robin"
    assert cfg.openai_agent_model == "gpt-agent"
    assert cfg.google_drive_manual_kits_folder_id == "drive-folder"


def test_config_raises_on_missing_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError, match="OPENAI_API_KEY"):
        Config.from_env()


def test_config_loads_meta_page_id(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("META_PAGE_ID", "123456789")
    monkeypatch.setenv("META_IG_USER_ID", "987654321")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://fleet.nayzfreedom.cloud")
    cfg = Config.from_env()
    assert cfg.meta_page_id == "123456789"
    assert cfg.meta_ig_user_id == "987654321"
    assert cfg.public_base_url == "https://fleet.nayzfreedom.cloud"


def test_config_meta_fields_default_empty(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.delenv("META_PAGE_ID", raising=False)
    monkeypatch.delenv("META_IG_USER_ID", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("OPS_PUBLIC_BASE_URL", raising=False)
    cfg = Config.from_env()
    assert cfg.meta_page_id == ""
    assert cfg.meta_ig_user_id == ""
    assert cfg.public_base_url == "https://fleet.nayzfreedom.cloud"
