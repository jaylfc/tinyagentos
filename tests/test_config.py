import pytest
import yaml
from tinyagentos.config import AppConfig, load_config, save_config, validate_config

class TestLoadConfig:
    def test_loads_valid_config(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.server["host"] == "0.0.0.0"
        assert config.server["port"] == 8888
        assert len(config.backends) == 1
        assert config.backends[0]["name"] == "test-backend"
        assert config.qmd["url"] == "http://localhost:7832"
        assert len(config.agents) == 1
        assert config.agents[0]["name"] == "test-agent"

    def test_returns_defaults_when_file_missing(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.server["port"] == 8888
        assert config.backends == []
        assert config.agents == []

    def test_rejects_invalid_yaml(self, tmp_path):
        bad = tmp_path / "config.yaml"
        bad.write_text(": : : not valid yaml [[[")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_config(bad)

class TestSaveConfig:
    def test_roundtrip(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        config.agents.append({"name": "new-agent", "host": "10.0.0.1", "qmd_index": "new", "color": "#fff"})
        save_config(config, tmp_data_dir / "config.yaml")
        reloaded = load_config(tmp_data_dir / "config.yaml")
        assert len(reloaded.agents) == 2
        assert reloaded.agents[1]["name"] == "new-agent"

class TestValidateConfig:
    def test_valid_config_passes(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        errors = validate_config(config)
        assert errors == []

    def test_missing_backend_url(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        del config.backends[0]["url"]
        errors = validate_config(config)
        assert any("url" in e for e in errors)

    def test_invalid_backend_type(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        config.backends[0]["type"] = "unsupported"
        errors = validate_config(config)
        assert any("type" in e for e in errors)

    def test_duplicate_agent_names(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        config.agents.append(config.agents[0].copy())
        errors = validate_config(config)
        assert any("duplicate" in e.lower() for e in errors)
