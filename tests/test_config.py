import pytest
import yaml
from tinyagentos.config import AppConfig, load_config, save_config, validate_config, normalize_agent

class TestLoadConfig:
    def test_loads_valid_config(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.server["host"] == "0.0.0.0"
        assert config.server["port"] == 6969
        assert len(config.backends) == 1
        assert config.backends[0]["name"] == "test-backend"
        assert config.qmd["url"] == "http://localhost:7832"
        assert len(config.agents) == 1
        assert config.agents[0]["name"] == "test-agent"

    def test_returns_defaults_when_file_missing(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.server["port"] == 6969
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

    def test_invalid_on_worker_failure(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        config.agents[0]["on_worker_failure"] = "magic"
        errors = validate_config(config)
        assert any("on_worker_failure" in e for e in errors)

    def test_valid_on_worker_failure_values(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        for value in ("pause", "fallback", "escalate-immediately"):
            config.agents[0]["on_worker_failure"] = value
            errors = validate_config(config)
            assert not any("on_worker_failure" in e for e in errors), \
                f"Expected '{value}' to be valid but got errors: {errors}"

    def test_fallback_models_must_be_list(self, tmp_data_dir):
        config = load_config(tmp_data_dir / "config.yaml")
        config.agents[0]["fallback_models"] = "not-a-list"
        errors = validate_config(config)
        assert any("fallback_models" in e for e in errors)


class TestWorkerFailureDefaults:
    def test_old_config_gets_defaults_on_load(self, tmp_path):
        """An old config without the new fields should load without error and have defaults."""
        old_config = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [
                {"name": "b", "type": "rkllama", "url": "http://localhost:8080", "priority": 1}
            ],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [
                {"name": "legacy-agent", "host": "192.168.1.50", "color": "#abc123"}
            ],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(old_config))
        config = load_config(p)
        agent = config.agents[0]
        assert agent["on_worker_failure"] == "pause"
        assert agent["fallback_models"] == []
        assert agent["paused"] is False

    def test_old_config_with_fallback_models_defaults_to_fallback_policy(self, tmp_path):
        """Old config that somehow has fallback_models but no policy defaults to 'fallback'."""
        old_config = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [
                {
                    "name": "agent-with-fallbacks",
                    "host": "10.0.0.1",
                    "color": "#fff",
                    "fallback_models": ["phi3", "llama3"],
                }
            ],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(old_config))
        config = load_config(p)
        agent = config.agents[0]
        assert agent["on_worker_failure"] == "fallback"

    def test_existing_policy_not_overwritten(self, tmp_path):
        """Explicitly set policy is preserved through load."""
        cfg_data = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [
                {
                    "name": "explicit-agent",
                    "host": "10.0.0.2",
                    "color": "#fff",
                    "on_worker_failure": "escalate-immediately",
                    "fallback_models": ["gpt-4o"],
                    "paused": False,
                }
            ],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(cfg_data))
        config = load_config(p)
        agent = config.agents[0]
        assert agent["on_worker_failure"] == "escalate-immediately"
        assert agent["fallback_models"] == ["gpt-4o"]

    def test_roundtrip_preserves_new_fields(self, tmp_path):
        """save_config + load_config preserves the new fields correctly."""
        p = tmp_path / "config.yaml"
        config = AppConfig(
            agents=[
                {
                    "name": "roundtrip-agent",
                    "host": "10.0.0.3",
                    "color": "#fff",
                    "on_worker_failure": "fallback",
                    "fallback_models": ["mistral", "phi3"],
                    "paused": False,
                }
            ],
            config_path=p,
        )
        save_config(config, p)
        reloaded = load_config(p)
        agent = reloaded.agents[0]
        assert agent["on_worker_failure"] == "fallback"
        assert agent["fallback_models"] == ["mistral", "phi3"]
        assert agent["paused"] is False

    def test_normalize_agent_idempotent(self):
        """Calling normalize_agent twice gives the same result."""
        agent = {"name": "x", "host": "h", "color": "#fff"}
        normalize_agent(agent)
        first = dict(agent)
        normalize_agent(agent)
        assert agent == first

class TestKvCacheQuantField:
    def test_old_config_gets_kv_quant_default(self, tmp_path):
        """Old config without kv_cache_quant loads with default 'fp16'."""
        old_config = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [{"name": "a", "host": "h", "color": "#abc"}],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(old_config))
        config = load_config(p)
        assert config.agents[0]["kv_cache_quant"] == "fp16"

    def test_explicit_value_preserved(self, tmp_path):
        cfg_data = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [{
                "name": "a",
                "host": "h",
                "color": "#abc",
                "kv_cache_quant": "turboquant-k3v2",
            }],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(cfg_data))
        config = load_config(p)
        assert config.agents[0]["kv_cache_quant"] == "turboquant-k3v2"

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "config.yaml"
        config = AppConfig(
            agents=[{
                "name": "kv-agent",
                "host": "10.0.0.1",
                "color": "#fff",
                "kv_cache_quant": "turboquant-k3v2",
            }],
            config_path=p,
        )
        save_config(config, p)
        reloaded = load_config(p)
        assert reloaded.agents[0]["kv_cache_quant"] == "turboquant-k3v2"

    def test_normalize_agent_idempotent_with_kv_quant(self):
        agent = {"name": "x", "host": "h", "color": "#fff", "kv_cache_quant": "fp16"}
        normalize_agent(agent)
        first = dict(agent)
        normalize_agent(agent)
        assert agent == first

    def test_any_string_accepted_no_validation(self, tmp_path):
        """validate_config does not restrict kv_cache_quant to a fixed list."""
        cfg_data = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [{
                "name": "future-agent",
                "host": "10.0.0.1",
                "color": "#fff",
                "kv_cache_quant": "some-future-scheme-v99",
            }],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(cfg_data))
        config = load_config(p)
        errors = validate_config(config)
        # No error for an unknown KV quant value — worker probe is source of truth.
        assert not any("kv_cache_quant" in e for e in errors)


    def test_paused_field_defaults_to_false(self, tmp_path):
        old_config = {
            "server": {"host": "0.0.0.0", "port": 6969},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [{"name": "a", "host": "h", "color": "#abc"}],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(old_config))
        config = load_config(p)
        assert config.agents[0]["paused"] is False
