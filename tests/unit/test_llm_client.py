"""Unit tests for AnthropicClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.agents.llm_client import AnthropicClient
from seraph.exceptions import LLMError, LLMRateLimitError


def _make_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    block.type = "text"
    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(input_tokens=10, output_tokens=20)
    return response


def _make_tool_response(text: str, tool_calls: list[dict]) -> MagicMock:
    blocks = []
    text_block = MagicMock()
    text_block.text = text
    text_block.type = "text"
    blocks.append(text_block)
    for tc in tool_calls:
        tb = MagicMock()
        tb.type = "tool_use"
        tb.id = tc["id"]
        tb.name = tc["name"]
        tb.input = tc["input"]
        blocks.append(tb)
    response = MagicMock()
    response.content = blocks
    response.usage = MagicMock(input_tokens=10, output_tokens=20)
    return response


class TestAnthropicClientComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_content(self) -> None:
        client = AnthropicClient(api_key="test-key", cache_enabled=False)
        mock_response = _make_response("Hello from Claude")

        with patch.object(client._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.complete([{"role": "user", "content": "Hi"}])

        assert result == "Hello from Claude"

    @pytest.mark.asyncio
    async def test_complete_caches_identical_requests(self) -> None:
        client = AnthropicClient(api_key="test-key", cache_enabled=True)
        mock_response = _make_response("Cached response")

        with patch.object(client._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            r1 = await client.complete([{"role": "user", "content": "same"}])
            r2 = await client.complete([{"role": "user", "content": "same"}])

        assert r1 == r2
        assert mock_create.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_raises_llm_error_on_api_failure(self) -> None:
        client = AnthropicClient(api_key="test-key", cache_enabled=False)

        with patch.object(client._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RuntimeError("API down")
            with pytest.raises(LLMError, match="API down"):
                await client.complete([{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_complete_retries_on_rate_limit(self) -> None:
        from anthropic import RateLimitError

        client = AnthropicClient(api_key="test-key", cache_enabled=False, max_retries=2)
        mock_response = _make_response("OK after retry")

        with patch.object(client._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [
                RateLimitError("rate limited", response=MagicMock(), body={}),
                mock_response,
            ]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.complete([{"role": "user", "content": "Hi"}])

        assert result == "OK after retry"
        assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_complete_raises_rate_limit_error_after_max_retries(self) -> None:
        from anthropic import RateLimitError

        client = AnthropicClient(api_key="test-key", cache_enabled=False, max_retries=1)

        with patch.object(client._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RateLimitError("rate limited", response=MagicMock(), body={})
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(LLMRateLimitError):
                    await client.complete([{"role": "user", "content": "Hi"}])


class TestAnthropicClientCompleteWithTools:
    @pytest.mark.asyncio
    async def test_complete_with_tools_returns_tool_calls(self) -> None:
        client = AnthropicClient(api_key="test-key", cache_enabled=False)
        mock_response = _make_tool_response(
            "Running nmap",
            [{"id": "tool-1", "name": "nmap", "input": {"ports": "80"}}],
        )

        tools = [{"name": "nmap", "description": "scan", "input_schema": {}}]
        with patch.object(client._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            text, tool_calls = await client.complete_with_tools(
                [{"role": "user", "content": "scan"}], tools
            )

        assert text == "Running nmap"
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "nmap"
