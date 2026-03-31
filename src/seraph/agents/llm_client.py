"""Async Anthropic API client with caching and retry logic.

Wraps ``anthropic.AsyncAnthropic`` and provides:
- Content-hash TTL cache for identical completions.
- Exponential backoff retry on rate-limit errors.
- Structured logging for every API call.

Usage::

    client = AnthropicClient(api_key="sk-ant-...", default_model="claude-sonnet-4-20250514")
    text = await client.complete(messages=[{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

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


class AnthropicClient:
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
        messages: list[dict[str, str]],
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
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Send a chat completion with tool-use enabled.

        Args:
            messages: Conversation history.
            tools: Anthropic tool definitions (name, description, input_schema).
            model: Override the default model.
            max_tokens: Maximum tokens in the response.
            system: Optional system prompt.

        Returns:
            Tuple of (assistant_text, tool_use_blocks).
            ``tool_use_blocks`` is empty when the model did not call any tools.

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

        text, tool_calls = await self._call_with_tools_retry(kwargs)
        return text, tool_calls

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
    ) -> tuple[str, list[dict[str, Any]]]:
        """Call ``messages.create`` with tools, retry on rate limit."""
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.messages.create(**kwargs)
                text = ""
                tool_calls: list[dict[str, Any]] = []
                for block in response.content:
                    if getattr(block, "type", None) == "text":
                        text += block.text
                    elif block.type == "tool_use":
                        tool_calls.append(
                            {"id": block.id, "name": block.name, "input": block.input}
                        )
                log.debug(
                    "llm_client.complete_with_tools",
                    model=kwargs["model"],
                    tool_calls=len(tool_calls),
                )
                return text, tool_calls
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
        messages: list[dict[str, str]],
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
