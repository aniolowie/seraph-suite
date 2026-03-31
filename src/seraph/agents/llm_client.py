"""LLM clients for Seraph Suite: Anthropic cloud API and local Ollama models.

Provides:
- ``BaseLLMClient``: abstract interface with ``complete`` and ``complete_with_tools``.
- ``AnthropicClient``: production client backed by Anthropic's API with TTL caching
  and exponential-backoff retry.
- ``LocalModelClient``: client backed by any Ollama-compatible local model server
  (e.g. ``qwen2.5-coder:8b``). Translates the Anthropic message/tool format used
  internally by Seraph to the OpenAI-compatible REST format Ollama exposes.

Usage::

    # Cloud
    client = AnthropicClient(api_key="sk-ant-...", default_model="claude-sonnet-4-20250514")
    text = await client.complete(messages=[{"role": "user", "content": "Hello"}])

    # Local
    client = LocalModelClient(base_url="http://localhost:11434", model_name="qwen2.5-coder:8b")
    text = await client.complete(messages=[{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog
from anthropic import AsyncAnthropic, RateLimitError

from seraph.exceptions import LLMError, LLMRateLimitError

log = structlog.get_logger(__name__)

_DEFAULT_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds


class _CacheEntry:
    __slots__ = ("expires_at", "value")

    def __init__(self, value: str, ttl: int) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl


# ── Abstract base ─────────────────────────────────────────────────────────────


class BaseLLMClient(ABC):
    """Common interface for all Seraph LLM back-ends."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> str:
        """Send a chat completion and return the assistant text."""

    @abstractmethod
    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Send a chat completion with tool-use enabled.

        Returns:
            Tuple of (assistant_text, tool_use_blocks, raw_content_blocks).
            ``raw_content_blocks`` is the full assistant content list — use it
            as the ``content`` field when appending the assistant message so
            that tool_use blocks are included and the conversation stays valid.
        """


# ── Anthropic cloud client ────────────────────────────────────────────────────


class AnthropicClient(BaseLLMClient):
    """Async Anthropic API wrapper with TTL cache and exponential-backoff retry.

    Args:
        api_key: Anthropic API key.
        default_model: Model ID used when callers don't specify one.
        cache_enabled: Whether to cache identical completions.
        cache_ttl_seconds: How long cached responses remain valid.
        max_retries: Maximum number of retries on rate-limit errors.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model
        self._cache_enabled = cache_enabled
        self._cache_ttl = cache_ttl_seconds
        self._max_retries = max_retries
        self._cache: dict[str, _CacheEntry] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> str:
        """Send a chat completion and return the assistant text.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            model: Override the default model.
            max_tokens: Maximum tokens in the response.
            system: Optional system prompt.

        Returns:
            Assistant response text.

        Raises:
            LLMRateLimitError: If rate limit persists after max retries.
            LLMError: On any other Anthropic API error.
        """
        resolved_model = model or self._default_model
        cache_key = self._cache_key(messages, resolved_model, max_tokens, system)

        if self._cache_enabled:
            cached = self._get_cached(cache_key)
            if cached is not None:
                log.debug("llm_client.cache_hit", model=resolved_model)
                return cached

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        text = await self._call_with_retry(kwargs)

        if self._cache_enabled:
            self._cache[cache_key] = _CacheEntry(text, self._cache_ttl)

        return text

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Send a chat completion with tool-use enabled.

        Args:
            messages: Conversation history.
            tools: Anthropic tool definitions (name, description, input_schema).
            model: Override the default model.
            max_tokens: Maximum tokens in the response.
            system: Optional system prompt.

        Returns:
            Tuple of (assistant_text, tool_use_blocks, raw_content_blocks).
            ``raw_content_blocks`` is the full assistant content list — use it
            as the ``content`` field when appending the assistant message so
            that tool_use blocks are included and the conversation stays valid
            for the Anthropic API.

        Raises:
            LLMRateLimitError: Rate limit after max retries.
            LLMError: On other API errors.
        """
        resolved_model = model or self._default_model
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
        }
        if system:
            kwargs["system"] = system

        return await self._call_with_tools_retry(kwargs)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _call_with_retry(self, kwargs: dict[str, Any]) -> str:
        """Call ``messages.create`` with exponential-backoff retry."""
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.messages.create(**kwargs)
                text = "".join(
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                )
                log.debug(
                    "llm_client.complete",
                    model=kwargs["model"],
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                return text
            except RateLimitError as exc:
                if attempt >= self._max_retries:
                    raise LLMRateLimitError(
                        f"Rate limit after {self._max_retries} retries"
                    ) from exc
                delay = _RETRY_BASE_DELAY * (2**attempt)
                log.warning("llm_client.rate_limit", attempt=attempt, delay=delay)
                await asyncio.sleep(delay)
            except Exception as exc:
                raise LLMError(f"Anthropic API error: {exc}") from exc
        raise LLMError("Unreachable retry loop exit")  # pragma: no cover

    async def _call_with_tools_retry(
        self, kwargs: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Call ``messages.create`` with tools, retry on rate limit.

        Returns:
            Tuple of (text, tool_calls, raw_content_blocks) where
            ``raw_content_blocks`` is the full content list to store as the
            assistant message — required for valid tool_use/tool_result turns.
        """
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.messages.create(**kwargs)
                text = ""
                tool_calls: list[dict[str, Any]] = []
                raw_blocks: list[dict[str, Any]] = []
                for block in response.content:
                    if getattr(block, "type", None) == "text":
                        text += block.text
                        raw_blocks.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        tool_calls.append(
                            {"id": block.id, "name": block.name, "input": block.input}
                        )
                        raw_blocks.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                log.debug(
                    "llm_client.complete_with_tools",
                    model=kwargs["model"],
                    tool_calls=len(tool_calls),
                )
                return text, tool_calls, raw_blocks
            except RateLimitError as exc:
                if attempt >= self._max_retries:
                    raise LLMRateLimitError(
                        f"Rate limit after {self._max_retries} retries"
                    ) from exc
                delay = _RETRY_BASE_DELAY * (2**attempt)
                log.warning("llm_client.rate_limit_tools", attempt=attempt, delay=delay)
                await asyncio.sleep(delay)
            except Exception as exc:
                raise LLMError(f"Anthropic API error: {exc}") from exc
        raise LLMError("Unreachable retry loop exit")  # pragma: no cover



    def _cache_key(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        system: str | None,
    ) -> str:
        payload = json.dumps(
            {"messages": messages, "model": model, "max_tokens": max_tokens, "system": system},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _get_cached(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.value


# ── Local model client (Ollama / OpenAI-compatible) ───────────────────────────


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-format messages to OpenAI/Ollama chat format.

    Handles three cases that arise during a tool-use conversation:
    1. Simple string content → passed through unchanged.
    2. Assistant messages with ``tool_use`` blocks → converted to OpenAI
       ``tool_calls`` fields.
    3. User messages with ``tool_result`` blocks → split into one
       ``{"role": "tool", ...}`` message per result.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        # content is a list of blocks
        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                btype = block.get("type") if isinstance(block, dict) else None
                if btype == "text":
                    text_parts.append(block["text"])
                elif btype == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })
            out: dict[str, Any] = {"role": "assistant"}
            out["content"] = "\n".join(text_parts) if text_parts else None
            if tool_calls:
                out["tool_calls"] = tool_calls
            result.append(out)

        elif role == "user":
            tool_results = [
                b for b in content
                if isinstance(b, dict) and b.get("type") == "tool_result"
            ]
            other_blocks = [
                b for b in content
                if not isinstance(b, dict) or b.get("type") != "tool_result"
            ]
            for tr in tool_results:
                tr_content = tr.get("content", "")
                if not isinstance(tr_content, str):
                    tr_content = json.dumps(tr_content)
                result.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_use_id"],
                    "content": tr_content,
                })
            if other_blocks:
                text = " ".join(
                    b.get("text", "") for b in other_blocks if isinstance(b, dict)
                )
                if text:
                    result.append({"role": "user", "content": text})

        else:
            result.append(msg)

    return result


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic tool definitions to OpenAI function-call format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


class LocalModelClient(BaseLLMClient):
    """LLM client for locally-hosted models via Ollama's OpenAI-compatible API.

    Converts Seraph's internal Anthropic message/tool format to the OpenAI
    REST format used by Ollama, so the same agent code works unchanged.

    Args:
        base_url: Ollama server base URL (default ``http://localhost:11434``).
        model_name: Model tag to use (e.g. ``qwen2.5-coder:8b``).
        cache_enabled: Whether to cache identical completions.
        cache_ttl_seconds: TTL for cached responses.
        max_retries: Retries on transient HTTP errors.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5-coder:8b",
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._cache_enabled = cache_enabled
        self._cache_ttl = cache_ttl_seconds
        self._max_retries = max_retries
        self._timeout = timeout
        self._cache: dict[str, _CacheEntry] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> str:
        """Send a chat completion and return the assistant text.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
                Anthropic tool-use message formats are automatically converted.
            model: Ignored — the configured ``model_name`` is always used.
            max_tokens: Maximum tokens in the response.
            system: Optional system prompt prepended as a system message.

        Returns:
            Assistant response text.

        Raises:
            LLMError: On any HTTP or parsing error.
        """
        oai_messages = self._build_messages(messages, system)
        cache_key = self._cache_key(oai_messages, max_tokens)

        if self._cache_enabled:
            cached = self._get_cached(cache_key)
            if cached is not None:
                log.debug("local_llm.cache_hit", model=self._model_name)
                return cached

        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = await self._post("/v1/chat/completions", payload)
        text = data["choices"][0]["message"]["content"] or ""

        if self._cache_enabled:
            self._cache[cache_key] = _CacheEntry(text, self._cache_ttl)

        log.debug("local_llm.complete", model=self._model_name)
        return text

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Send a chat completion with tool-use enabled.

        Args:
            messages: Conversation history (Anthropic format is auto-converted).
            tools: Anthropic tool definitions (name, description, input_schema).
            model: Ignored — the configured ``model_name`` is always used.
            max_tokens: Maximum tokens in the response.
            system: Optional system prompt.

        Returns:
            Tuple of (assistant_text, tool_use_blocks, raw_content_blocks).
            Both ``tool_use_blocks`` and ``raw_content_blocks`` use Anthropic
            format so the state remains consistent with ``AnthropicClient``
            output and message-format converters work on subsequent turns.

        Raises:
            LLMError: On HTTP or parsing errors.
        """
        oai_messages = self._build_messages(messages, system)
        oai_tools = _to_openai_tools(tools)

        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if oai_tools:
            payload["tools"] = oai_tools

        data = await self._post_with_retry("/v1/chat/completions", payload)
        choice = data["choices"][0]
        msg = choice["message"]

        text = msg.get("content") or ""
        tool_calls_raw = msg.get("tool_calls") or []

        # Convert OpenAI tool_calls → Anthropic format expected by agents
        tool_calls: list[dict[str, Any]] = []
        raw_blocks: list[dict[str, Any]] = []

        if text:
            raw_blocks.append({"type": "text", "text": text})

        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            try:
                arguments = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}
            call_id = tc.get("id", f"local_{len(tool_calls)}")
            tool_calls.append({"id": call_id, "name": fn.get("name", ""), "input": arguments})
            raw_blocks.append({
                "type": "tool_use",
                "id": call_id,
                "name": fn.get("name", ""),
                "input": arguments,
            })

        log.debug(
            "local_llm.complete_with_tools",
            model=self._model_name,
            tool_calls=len(tool_calls),
        )
        return text, tool_calls, raw_blocks

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_messages(
        self,
        messages: list[dict[str, Any]],
        system: str | None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(_to_openai_messages(messages))
        return out

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to the Ollama API and return the parsed JSON body."""
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"Local model HTTP {exc.response.status_code}: {exc.response.text[:400]}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Local model connection error: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Local model error: {exc}") from exc

    async def _post_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with exponential-backoff retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._post(path, payload)
            except LLMError as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    log.warning("local_llm.retry", attempt=attempt, delay=delay, error=str(exc))
                    await asyncio.sleep(delay)
        raise last_exc or LLMError("Unreachable retry loop exit")  # pragma: no cover

    def _cache_key(self, messages: list[dict[str, Any]], max_tokens: int) -> str:
        payload = json.dumps(
            {"messages": messages, "model": self._model_name, "max_tokens": max_tokens},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _get_cached(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.value
