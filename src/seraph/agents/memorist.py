"""Memorist agent — self-learning loop trigger on engagement completion.

The Memorist runs as a terminal-edge node in the LangGraph graph (after
the orchestrator decides "done").  It:

1. Asks the LLM to identify which KB documents were cited during the run.
2. Persists a FeedbackRecord with cited vs. uncited doc IDs.
3. Calls HardNegativeMiner to create training triplets from the diff.

LoRA fine-tuning is intentionally NOT triggered here — it runs on the
Celery beat schedule (every N hours) to batch multiple engagements.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from seraph.agents.base_agent import BaseAgent
from seraph.agents.state import EngagementState
from seraph.exceptions import FeedbackError

log = structlog.get_logger(__name__)

_JSON_RE = re.compile(r"\{[^{}]*\"cited_doc_ids\"[^{}]*\}", re.DOTALL)
_MULTILINE_JSON_RE = re.compile(r"\{.*?\"cited_doc_ids\".*?\}", re.DOTALL)


class MemoristAgent(BaseAgent):
    """Terminal agent that logs KB citation feedback and mines hard negatives.

    Args:
        feedback_db: FeedbackDB instance for persisting citations.
        vector_store: QdrantStore used by HardNegativeMiner.
        engagement_id: Unique identifier for the current engagement.
        All other args forwarded to BaseAgent.
    """

    AGENT_NAME = "memorist"

    def __init__(
        self,
        *args: Any,
        feedback_db: Any | None = None,
        vector_store: Any | None = None,
        engagement_id: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._feedback_db = feedback_db
        self._vector_store = vector_store
        self._engagement_id = engagement_id

    async def run(self, state: EngagementState) -> EngagementState:
        """Log citation feedback and mine hard negatives.

        Steps:
        1. Ask LLM to identify which KB docs were actually cited.
        2. Persist FeedbackRecord with cited/uncited split.
        3. Run HardNegativeMiner to produce training triplets.
        4. Return state with ``cited_doc_ids`` updated.

        Args:
            state: Final engagement state after all agents have run.

        Returns:
            State with ``cited_doc_ids`` populated.
        """
        state = state.model_copy(update={"current_agent": self.AGENT_NAME})

        if not state.kb_context:
            log.info("memorist.no_kb_context_skip")
            return state

        cited_ids = await self._extract_citations(state)
        all_retrieved_ids = [doc.id for doc in state.kb_context]

        state = state.model_copy(update={"cited_doc_ids": cited_ids})

        if self._feedback_db is not None:
            await self._persist_feedback(
                state=state,
                all_retrieved_ids=all_retrieved_ids,
                cited_ids=cited_ids,
            )

        state = self._append_history(
            state,
            action="memorist_feedback_logged",
            input_data={
                "retrieved_docs": len(all_retrieved_ids),
                "cited_docs": len(cited_ids),
            },
            output=f"Logged {len(cited_ids)}/{len(all_retrieved_ids)} cited docs",
        )
        log.info(
            "memorist.complete",
            cited=len(cited_ids),
            uncited=len(all_retrieved_ids) - len(cited_ids),
        )
        return state

    async def _extract_citations(self, state: EngagementState) -> list[str]:
        """Ask the LLM which KB docs were cited, return their IDs."""
        if not state.kb_context:
            return []

        system_prompt = self._render_prompt(
            "memorist.jinja2",
            target=state.target,
            phase=state.phase.value,
            iteration=state.iteration,
            flags=state.flags,
            findings=state.findings,
            kb_context=state.kb_context,
            history=state.history,
        )

        messages = [{"role": "user", "content": "Identify which KB documents were cited."}]

        try:
            text = await self._llm.complete(
                messages,
                system=system_prompt,
                max_tokens=1024,
            )
        except Exception as exc:
            log.warning("memorist.llm_failed", error=str(exc))
            return []

        return _parse_cited_ids(text)

    async def _persist_feedback(
        self,
        state: EngagementState,
        all_retrieved_ids: list[str],
        cited_ids: list[str],
    ) -> None:
        """Persist FeedbackRecord and mine hard negatives."""
        engagement_id = self._engagement_id or str(id(state))

        # Build a synthetic combined query from the engagement
        query = _build_engagement_query(state)

        try:
            record_id = await self._feedback_db.log_retrieval(
                engagement_id=engagement_id,
                agent_name=self.AGENT_NAME,
                query=query,
                retrieved_doc_ids=all_retrieved_ids,
            )
            await self._feedback_db.mark_citations(
                record_id=record_id,
                cited_doc_ids=cited_ids,
            )
        except FeedbackError as exc:
            log.warning("memorist.feedback_persist_failed", error=str(exc))
            return

        if self._vector_store is not None:
            try:
                from seraph.learning.negatives import HardNegativeMiner

                miner = HardNegativeMiner(
                    feedback_db=self._feedback_db,
                    vector_store=self._vector_store,
                )
                triplets = await miner.mine(engagement_id=engagement_id)
                log.info("memorist.triplets_mined", count=len(triplets))
            except Exception as exc:
                log.warning("memorist.mining_failed", error=str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_cited_ids(text: str) -> list[str]:
    """Extract cited_doc_ids list from LLM JSON output."""
    for pattern in (_MULTILINE_JSON_RE, _JSON_RE):
        match = pattern.search(text)
        if match:
            try:
                data = json.loads(match.group())
                ids = data.get("cited_doc_ids", [])
                if isinstance(ids, list):
                    return [str(i) for i in ids]
            except json.JSONDecodeError:
                continue
    return []


def _build_engagement_query(state: EngagementState) -> str:
    """Construct a representative query string from the engagement state."""
    parts: list[str] = [f"pentest {state.target.ip}"]
    if state.target.os:
        parts.append(state.target.os)
    for finding in state.findings[-5:]:
        parts.append(finding.title)
        parts.extend(finding.mitre_techniques[:2])
    return " ".join(parts)
