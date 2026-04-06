import pytest
from tinyagentos.llm_proxy import generate_litellm_config, LLMProxy


class TestConfigGeneration:
    def test_generates_config_from_backends(self):
        backends = [
            {"name": "fedora-gpu", "type": "ollama", "url": "http://fedora:11434", "priority": 1},
            {"name": "local-npu", "type": "rkllama", "url": "http://localhost:8080", "priority": 3},
        ]
        config = generate_litellm_config(backends)
        assert "model_list" in config
        assert len(config["model_list"]) >= 2
        # First entry should be highest priority
        assert config["model_list"][0]["litellm_params"]["api_base"] == "http://fedora:11434"

    def test_empty_backends_returns_empty_model_list(self):
        config = generate_litellm_config([])
        assert config["model_list"] == []

    def test_ollama_backend_uses_ollama_prefix(self):
        backends = [{"name": "local", "type": "ollama", "url": "http://localhost:11434", "priority": 1}]
        config = generate_litellm_config(backends)
        model_param = config["model_list"][0]["litellm_params"]["model"]
        assert model_param.startswith("ollama/") or model_param.startswith("ollama_chat/")

    def test_openai_backend_uses_direct_model(self):
        backends = [{"name": "cloud", "type": "openai", "url": "https://api.openai.com", "priority": 1, "api_key_secret": "openai-key"}]
        config = generate_litellm_config(backends)
        assert "api_base" not in config["model_list"][0]["litellm_params"] or config["model_list"][0]["litellm_params"]["api_base"] == "https://api.openai.com"

    def test_rkllama_treated_as_ollama_compat(self):
        backends = [{"name": "npu", "type": "rkllama", "url": "http://localhost:8080", "priority": 1}]
        config = generate_litellm_config(backends)
        # rkllama is ollama-compatible
        model_param = config["model_list"][0]["litellm_params"]["model"]
        assert "ollama" in model_param.lower() or config["model_list"][0]["litellm_params"].get("api_base")


class TestLLMProxy:
    def test_proxy_not_running_initially(self):
        proxy = LLMProxy(port=14000)
        assert not proxy.is_running()

    def test_proxy_url(self):
        proxy = LLMProxy(port=14000)
        assert proxy.url == "http://localhost:14000"
