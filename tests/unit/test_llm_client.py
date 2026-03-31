"""Unit tests for AnthropicClient and LocalModelClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.agents.llm_client import (
    AnthropicClient,
    LocalModelClient,
    _to_openai_messages,
    _to_openai_tools,
)
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
            text, tool_calls, raw_blocks = await client.complete_with_tools(
                [{"role": "user", "content": "scan"}], tools
            )

        assert text == "Running nmap"
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "nmap"


# ── LocalModelClient tests ────────────────────────────────────────────────────


def _make_ollama_response(text: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": None,
                }
            }
        ]
    }


def _make_ollama_tool_response(text: str, tool_calls: list[dict]) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["input"]),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            }
        ]
    }


class TestLocalModelClientComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_content(self) -> None:
        client = LocalModelClient(model_name="qwen2.5-coder:8b", cache_enabled=False)
        resp = _make_ollama_response("Hello from local model")

        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = resp
            result = await client.complete([{"role": "user", "content": "Hi"}])

        assert result == "Hello from local model"

    @pytest.mark.asyncio
    async def test_complete_caches_identical_requests(self) -> None:
        client = LocalModelClient(model_name="qwen2.5-coder:8b", cache_enabled=True)
        resp = _make_ollama_response("Cached")

        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = resp
            r1 = await client.complete([{"role": "user", "content": "same"}])
            r2 = await client.complete([{"role": "user", "content": "same"}])

        assert r1 == r2 == "Cached"
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_includes_system_as_message(self) -> None:
        client = LocalModelClient(model_name="qwen2.5-coder:8b", cache_enabled=False)
        resp = _make_ollama_response("ok")
        captured: list[dict] = []

        async def capture(path: str, payload: dict) -> dict:  # type: ignore[override]
            captured.append(payload)
            return resp

        with patch.object(client, "_post", side_effect=capture):
            await client.complete(
                [{"role": "user", "content": "hello"}],
                system="You are an expert.",
            )

        assert captured[0]["messages"][0] == {"role": "system", "content": "You are an expert."}

    @pytest.mark.asyncio
    async def test_complete_raises_llm_error_on_failure(self) -> None:
        client = LocalModelClient(model_name="qwen2.5-coder:8b", cache_enabled=False)

        with patch.object(client, "_post", new_callable=AsyncMock, side_effect=LLMError("down")):
            with pytest.raises(LLMError, match="down"):
                await client.complete([{"role": "user", "content": "Hi"}])


class TestLocalModelClientCompleteWithTools:
    @pytest.mark.asyncio
    async def test_complete_with_tools_returns_tool_calls(self) -> None:
        client = LocalModelClient(model_name="qwen2.5-coder:8b", cache_enabled=False)
        resp = _make_ollama_tool_response(
            "Running nmap",
            [{"id": "call-1", "name": "nmap", "input": {"ports": "80"}}],
        )

        tools = [{"name": "nmap", "description": "scan", "input_schema": {}}]
        with patch.object(client, "_post_with_retry", new_callable=AsyncMock, return_value=resp):
            text, tool_calls, raw_blocks = await client.complete_with_tools(
                [{"role": "user", "content": "scan"}], tools
            )

        assert text == "Running nmap"
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "nmap"
        assert tool_calls[0]["input"] == {"ports": "80"}

        assert any(b["type"] == "tool_use" and b["name"] == "nmap" for b in raw_blocks)

    @pytest.mark.asyncio
    async def test_complete_with_tools_no_tool_calls(self) -> None:
        client = LocalModelClient(model_name="qwen2.5-coder:8b", cache_enabled=False)
        resp = _make_ollama_response("I have no tools to call.")

        tools = [{"name": "nmap", "description": "scan", "input_schema": {}}]
        with patch.object(client, "_post_with_retry", new_callable=AsyncMock, return_value=resp):
            text, tool_calls, raw_blocks = await client.complete_with_tools(
                [{"role": "user", "content": "what?"}], tools
            )

        assert text == "I have no tools to call."
        assert tool_calls == []
        assert raw_blocks == [{"type": "text", "text": "I have no tools to call."}]


class TestToOpenaiMessages:
    def test_simple_string_content(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        result = _to_openai_messages(messages)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_assistant_tool_use_blocks(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Running nmap"},
                    {"type": "tool_use", "id": "tu-1", "name": "nmap", "input": {"ports": "80"}},
                ],
            }
        ]
        result = _to_openai_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Running nmap"
        assert result[0]["tool_calls"][0]["function"]["name"] == "nmap"

    def test_user_tool_result_blocks(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu-1",
                        "content": "exit_code=0\noutput",
                    },
                ],
            }
        ]
        result = _to_openai_messages(messages)
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tu-1"
        assert "output" in result[0]["content"]


class TestToOpenaiTools:
    def test_converts_anthropic_tools(self) -> None:
        tools = [{"name": "nmap", "description": "scan", "input_schema": {"type": "object"}}]
        result = _to_openai_tools(tools)
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "nmap"
        assert result[0]["function"]["parameters"] == {"type": "object"}
