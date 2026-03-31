"""Text chunking utilities for the ingestion pipeline.

Rules (from CLAUDE.md):
- Never split inside code blocks (``` markers).
- Chunk size: 200-500 tokens for prose, single-chunk for CVE descriptions.
- Prepend source tag to every chunk: "[CVE-2021-44228] ..."
"""

from __future__ import annotations

import re

# Simple whitespace-based token estimator — good enough for chunking decisions.
_TOKENS_PER_WORD: float = 1.3  # typical BPE multiplier


def _estimate_tokens(text: str) -> int:
    """Estimate token count using whitespace word count x 1.3."""
    return int(len(text.split()) * _TOKENS_PER_WORD)


def _split_preserving_code_blocks(text: str) -> list[tuple[str, bool]]:
    """Split text into segments tagged as (content, is_code_block).

    Code blocks (``` ... ```) are never merged with surrounding text.
    """
    segments: list[tuple[str, bool]] = []
    pattern = re.compile(r"```.*?```", re.DOTALL)
    last_end = 0

    for match in pattern.finditer(text):
        before = text[last_end : match.start()]
        if before.strip():
            segments.append((before, False))
        segments.append((match.group(), True))
        last_end = match.end()

    remainder = text[last_end:]
    if remainder.strip():
        segments.append((remainder, False))

    return segments


def chunk_text(
    text: str,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[str]:
    """Split ``text`` into overlapping chunks, never breaking inside code blocks.

    Args:
        text: Input text to chunk.
        max_tokens: Maximum estimated tokens per chunk.
        overlap_tokens: Number of tokens to repeat at the start of the next chunk.

    Returns:
        List of text chunks. Always at least one element.
    """
    if not text.strip():
        return []

    if _estimate_tokens(text) <= max_tokens:
        return [text.strip()]

    segments = _split_preserving_code_blocks(text)
    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    def _flush(overlap: list[str]) -> list[str]:
        """Emit current buffer as a chunk, return overlap tail."""
        joined = " ".join(current_parts).strip()
        if joined:
            chunks.append(joined)
        # Return the last few words for overlap
        words = joined.split()
        overlap_word_count = int(overlap_tokens / _TOKENS_PER_WORD)
        return [" ".join(words[-overlap_word_count:])] if overlap_word_count else []

    for content, is_code in segments:
        seg_tokens = _estimate_tokens(content)

        if is_code:
            # Code blocks are atomic — flush before and after if needed.
            if current_tokens + seg_tokens > max_tokens and current_parts:
                carry = _flush([])
                current_parts = carry[:]
                current_tokens = _estimate_tokens(" ".join(carry))
            current_parts.append(content)
            current_tokens += seg_tokens
        else:
            # Split prose by paragraphs.
            paragraphs = [p for p in re.split(r"\n\n+", content) if p.strip()]
            for para in paragraphs:
                para_tokens = _estimate_tokens(para)
                if current_tokens + para_tokens > max_tokens and current_parts:
                    carry = _flush([])
                    current_parts = carry[:]
                    current_tokens = _estimate_tokens(" ".join(carry))
                current_parts.append(para)
                current_tokens += para_tokens

    # Flush remaining
    if current_parts:
        joined = " ".join(current_parts).strip()
        if joined:
            chunks.append(joined)

    return chunks if chunks else [text.strip()]


def single_chunk(text: str, max_tokens: int = 500) -> str:
    """Return text as a single chunk, truncating to ``max_tokens`` if needed.

    Used for CVE descriptions which must not be split across chunks.

    Args:
        text: Input text.
        max_tokens: Token budget. Text is truncated by words if exceeded.

    Returns:
        The (possibly truncated) text.
    """
    if _estimate_tokens(text) <= max_tokens:
        return text.strip()
    words = text.split()
    target_words = int(max_tokens / _TOKENS_PER_WORD)
    return " ".join(words[:target_words])


def chunk_markdown(
    text: str,
    source: str,
    doc_id: str,
    metadata: dict[str, object] | None = None,
    max_tokens: int = 500,
) -> list[object]:
    """Chunk a markdown document and return a list of ``DocumentChunk`` objects.

    Wraps ``chunk_text`` and constructs ``DocumentChunk`` instances with the
    given source/doc_id metadata.  Prepends a source tag to every chunk.

    Args:
        text: Markdown body text (frontmatter already stripped).
        source: Source label (e.g. "writeup", "ctftime").
        doc_id: Stable identifier for the parent document (e.g. SHA256 hash).
        metadata: Extra payload fields passed to ``DocumentChunk.metadata``.
        max_tokens: Maximum tokens per chunk.

    Returns:
        List of ``DocumentChunk`` objects ready for embedding.
    """
    from seraph.ingestion.models import DocumentChunk

    raw_chunks = chunk_text(text, max_tokens=max_tokens)
    meta = dict(metadata) if metadata else {}
    title = str(meta.get("title", doc_id))

    chunks: list[DocumentChunk] = []
    for idx, chunk in enumerate(raw_chunks):
        tagged = prepend_source_tag(chunk, title)
        chunks.append(
            DocumentChunk(
                id=f"{doc_id}-{idx}",
                text=tagged,
                source=source,
                doc_type=source,
                metadata={**meta, "chunk_index": idx, "doc_id": doc_id},
            )
        )
    return chunks  # type: ignore[return-value]


def prepend_source_tag(text: str, tag: str) -> str:
    """Prepend a bracketed source tag to text.

    Example::

        prepend_source_tag("Apache Log4j2 ...", "CVE-2021-44228")
        # → "[CVE-2021-44228] Apache Log4j2 ..."

    Args:
        text: The text content.
        tag: Source identifier (CVE ID, EDB ID, etc.).

    Returns:
        Tagged text string.
    """
    return f"[{tag}] {text}"
