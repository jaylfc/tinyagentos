import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from tinyagentos.backend_adapters import (
    check_backend_health, RkLlamaAdapter, OllamaAdapter, LlamaCppAdapter, VllmAdapter, get_adapter,
)

class TestGetAdapter:
    def test_returns_rkllama(self):
        assert isinstance(get_adapter("rkllama"), RkLlamaAdapter)
    def test_returns_ollama(self):
        assert isinstance(get_adapter("ollama"), OllamaAdapter)
    def test_returns_llama_cpp(self):
        assert isinstance(get_adapter("llama-cpp"), LlamaCppAdapter)
    def test_returns_vllm(self):
        assert isinstance(get_adapter("vllm"), VllmAdapter)
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown backend type"):
            get_adapter("unknown")

class TestRkLlamaAdapter:
    @pytest.mark.asyncio
    async def test_parse_health_response(self):
        adapter = RkLlamaAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.raise_for_status = MagicMock(return_value=None)
        tags_response.json.return_value = {
            "models": [
                {"name": "qwen3-embedding-0.6b", "size": 892000000},
                {"name": "qwen3-reranker-0.6b", "size": 892000000},
            ]
        }
        mock_client.get.return_value = tags_response
        result = await adapter.health(mock_client, "http://localhost:8080")
        assert result["status"] == "ok"
        assert len(result["models"]) == 2
        assert result["models"][0]["name"] == "qwen3-embedding-0.6b"
        assert "response_ms" in result

    @pytest.mark.asyncio
    async def test_unreachable_returns_error(self):
        adapter = RkLlamaAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        result = await adapter.health(mock_client, "http://localhost:8080")
        assert result["status"] == "error"
        assert result["models"] == []

class TestOllamaAdapter:
    @pytest.mark.asyncio
    async def test_parse_tags_response(self):
        adapter = OllamaAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.raise_for_status = MagicMock(return_value=None)
        tags_response.json.return_value = {"models": [{"name": "llama3:latest", "size": 4700000000}]}
        mock_client.get.return_value = tags_response
        result = await adapter.health(mock_client, "http://localhost:11434")
        assert result["status"] == "ok"
        assert len(result["models"]) == 1
