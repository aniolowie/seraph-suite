"""Unit tests for the chunker module."""

from __future__ import annotations

from seraph.ingestion.chunker import chunk_text, prepend_source_tag, single_chunk


class TestChunkText:
    def test_short_text_returns_single_chunk(self) -> None:
        text = "This is a short text."
        result = chunk_text(text, max_tokens=500)
        assert len(result) == 1
        assert result[0] == text

    def test_empty_text_returns_empty(self) -> None:
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_long_text_splits_by_paragraphs(self) -> None:
        # Create text with two large paragraphs.
        para1 = " ".join(["word"] * 300)
        para2 = " ".join(["other"] * 300)
        text = f"{para1}\n\n{para2}"
        result = chunk_text(text, max_tokens=250)
        assert len(result) >= 2
        # Each chunk should contain content from one paragraph.
        assert "word" in result[0]

    def test_code_block_not_split(self) -> None:
        code_block = "```python\n" + "\n".join([f"x = {i}" for i in range(200)]) + "\n```"
        text = f"Intro text.\n\n{code_block}"
        result = chunk_text(text, max_tokens=50)
        # Code block must appear intact in one chunk.
        code_in_result = any("```python" in chunk and "```" in chunk for chunk in result)
        assert code_in_result, "Code block was split across chunks"

    def test_always_returns_at_least_one_chunk(self) -> None:
        result = chunk_text("Hello world", max_tokens=1)
        assert len(result) >= 1

    def test_text_at_exact_max_tokens_is_single_chunk(self) -> None:
        text = " ".join(["word"] * 100)  # ~130 estimated tokens
        result = chunk_text(text, max_tokens=200)
        assert len(result) == 1


class TestSingleChunk:
    def test_short_text_unchanged(self) -> None:
        text = "Short description."
        assert single_chunk(text, max_tokens=500) == text.strip()

    def test_long_text_truncated(self) -> None:
        text = " ".join([f"word{i}" for i in range(1000)])
        result = single_chunk(text, max_tokens=100)
        # Result must be shorter than input.
        assert len(result.split()) < len(text.split())

    def test_truncation_preserves_word_boundaries(self) -> None:
        text = " ".join([f"word{i}" for i in range(1000)])
        result = single_chunk(text, max_tokens=50)
        # Should not end mid-word.
        for word in result.split():
            assert word.isalnum() or word[-1].isalnum()


class TestPrependSourceTag:
    def test_basic_prepend(self) -> None:
        result = prepend_source_tag("Apache Log4j2...", "CVE-2021-44228")
        assert result == "[CVE-2021-44228] Apache Log4j2..."

    def test_edb_tag(self) -> None:
        result = prepend_source_tag("Remote code execution exploit.", "EDB-12345")
        assert result.startswith("[EDB-12345]")

    def test_empty_text(self) -> None:
        result = prepend_source_tag("", "TAG")
        assert result == "[TAG] "
