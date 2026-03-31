"""Hard negative mining for the self-learning loop.

A hard negative is a document that is keyword-similar to the query but
was NOT cited by the LLM, while a different document retrieved for the
same query WAS cited.  These are the most valuable negatives for
contrastive training.

Mining strategy:
1. Fetch all (record_id, query, uncited_doc_id) from FeedbackDB.
2. For each record, also fetch cited doc IDs.
3. For each (cited, uncited) pair, check BM25 overlap to confirm the
   negative is "hard" (non-trivially similar to the query).
4. Persist Triplets back to FeedbackDB.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

import structlog

from seraph.exceptions import HardNegativeError
from seraph.learning.models import Triplet

if TYPE_CHECKING:
    from seraph.knowledge.vectorstore import QdrantStore
    from seraph.learning.feedback import FeedbackDB

log = structlog.get_logger(__name__)

_TOKEN_RE = re.compile(r"\w+")
_MIN_BM25_OVERLAP = 2  # minimum shared tokens to qualify as a hard negative


def _token_set(text: str) -> set[str]:
    """Lowercase tokenise text into a set of word tokens."""
    return {m.lower() for m in _TOKEN_RE.findall(text)}


def _bm25_overlap(query: str, doc_text: str) -> int:
    """Count shared unique tokens between query and document."""
    return len(_token_set(query) & _token_set(doc_text))


class HardNegativeMiner:
    """Mines (query, positive, hard_negative) triplets from feedback data.

    Args:
        feedback_db: FeedbackDB instance for reading events and writing triplets.
        vector_store: QdrantStore for fetching document text by ID.
        min_overlap: Minimum shared query-doc tokens to qualify as hard negative.
    """

    def __init__(
        self,
        feedback_db: FeedbackDB,
        vector_store: QdrantStore,
        min_overlap: int = _MIN_BM25_OVERLAP,
    ) -> None:
        self._db = feedback_db
        self._store = vector_store
        self._min_overlap = min_overlap

    async def mine(
        self,
        engagement_id: str | None = None,
        limit: int = 500,
    ) -> list[Triplet]:
        """Mine hard negative triplets from recent feedback.

        Args:
            engagement_id: Restrict mining to one engagement (None = all).
            limit: Maximum uncited refs to process.

        Returns:
            List of newly created ``Triplet`` objects.

        Raises:
            HardNegativeError: On irrecoverable mining failure.
        """
        try:
            uncited_rows = await self._db.get_uncited_doc_ids(
                engagement_id=engagement_id, limit=limit
            )
        except Exception as exc:
            raise HardNegativeError(f"Failed to fetch uncited docs: {exc}") from exc

        if not uncited_rows:
            log.info("negatives.nothing_to_mine")
            return []

        # Group by record_id → {query, [uncited_doc_ids]}
        records: dict[str, dict[str, object]] = defaultdict(lambda: {"query": "", "uncited": []})
        for row in uncited_rows:
            rid = row["record_id"]
            records[rid]["query"] = row["query"]
            records[rid]["uncited"].append(row["doc_id"])  # type: ignore[union-attr]

        # Fetch full feedback records (to get cited doc IDs)
        triplets: list[Triplet] = []
        for record_id, data in records.items():
            query = str(data["query"])
            uncited_ids = list(data["uncited"])  # type: ignore[arg-type]

            record = await self._db.get_record(record_id)
            if record is None or not record.cited_doc_ids:
                continue

            # Fetch texts for positives and negatives from vector store
            all_ids = list(record.cited_doc_ids) + uncited_ids
            texts = await self._fetch_texts(all_ids)

            for pos_id in record.cited_doc_ids:
                pos_text = texts.get(pos_id, "")
                if not pos_text:
                    continue

                for neg_id in uncited_ids:
                    neg_text = texts.get(neg_id, "")
                    if not neg_text:
                        continue

                    if _bm25_overlap(query, neg_text) < self._min_overlap:
                        continue  # not a hard negative

                    triplet = Triplet(
                        query=query,
                        positive_doc_id=pos_id,
                        negative_doc_id=neg_id,
                        positive_text=pos_text,
                        negative_text=neg_text,
                        source="feedback",
                    )
                    triplets.append(triplet)

        # Persist triplets
        for t in triplets:
            try:
                await self._db.save_triplet(
                    query=t.query,
                    positive_doc_id=t.positive_doc_id,
                    negative_doc_id=t.negative_doc_id,
                    positive_text=t.positive_text,
                    negative_text=t.negative_text,
                    source=t.source,
                )
            except Exception as exc:
                log.warning("negatives.save_failed", error=str(exc))

        log.info(
            "negatives.mined",
            total_uncited=len(uncited_rows),
            triplets_created=len(triplets),
        )
        return triplets

    async def _fetch_texts(self, doc_ids: list[str]) -> dict[str, str]:
        """Fetch chunk texts from the vector store by doc ID.

        Returns a dict mapping doc_id → text.  Missing IDs are omitted.
        """
        if not doc_ids:
            return {}
        try:
            results = await self._store.fetch_by_ids(doc_ids)
            return {
                r.id: (r.payload.get("text", "") if r.payload else "")
                for r in results
                if r.id is not None
            }
        except Exception as exc:
            log.warning("negatives.fetch_texts_failed", error=str(exc))
            return {}
