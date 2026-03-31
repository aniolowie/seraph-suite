"""Regex-based entity extractor for attack graph query augmentation.

Extracts CVE IDs, MITRE technique/tactic IDs, and CWE IDs from free-text
queries.  Used as the first step in the GraphRAG pipeline to determine
whether graph traversal is warranted.

Example::

    extractor = EntityExtractor()
    entities = extractor.extract("CVE-2021-44228 Log4Shell exploitation T1190")
    # entities.cve_ids == ["CVE-2021-44228"]
    # entities.technique_ids == ["T1190"]
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# ── Compiled patterns ─────────────────────────────────────────────────────────

# CVE-YYYY-NNNNN (4-digit year, 4+ digit sequence)
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)

# MITRE ATT&CK technique: T1059 or T1059.001
_TECHNIQUE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")

# MITRE ATT&CK tactic: TA0001 … TA0099
_TACTIC_RE = re.compile(r"\bTA\d{4}\b")

# CWE identifier: CWE-79, CWE-89, etc.
_CWE_RE = re.compile(r"\bCWE-\d+\b", re.IGNORECASE)


class ExtractedEntities(BaseModel):
    """Entities extracted from a query string.

    All ID lists contain normalised uppercase strings with no duplicates.
    """

    cve_ids: list[str] = Field(default_factory=list)
    technique_ids: list[str] = Field(default_factory=list)
    tactic_ids: list[str] = Field(default_factory=list)
    cwe_ids: list[str] = Field(default_factory=list)

    @property
    def has_entities(self) -> bool:
        """True if any entity type was extracted."""
        return bool(self.cve_ids or self.technique_ids or self.tactic_ids or self.cwe_ids)

    @property
    def all_ids(self) -> list[str]:
        """Flat list of all extracted IDs."""
        return self.cve_ids + self.technique_ids + self.tactic_ids + self.cwe_ids


class EntityExtractor:
    """Extracts MITRE/CVE/CWE identifiers from free-text queries.

    Purely regex-based — no LLM call, no graph access.  Designed to be
    called synchronously at the start of the GraphRAG pipeline.
    """

    def extract(self, query: str) -> ExtractedEntities:
        """Extract entities from a query string.

        Args:
            query: Free-text query (e.g. user prompt or agent task description).

        Returns:
            ``ExtractedEntities`` with deduplicated, normalised IDs.
        """
        cve_ids = _dedupe_upper(_CVE_RE.findall(query))
        technique_ids = _dedupe(_TECHNIQUE_RE.findall(query))
        tactic_ids = _dedupe(_TACTIC_RE.findall(query))
        cwe_ids = _dedupe_upper(_CWE_RE.findall(query))

        return ExtractedEntities(
            cve_ids=cve_ids,
            technique_ids=technique_ids,
            tactic_ids=tactic_ids,
            cwe_ids=cwe_ids,
        )

    def extract_technique_ids(self, query: str) -> list[str]:
        """Extract only MITRE technique IDs.

        Args:
            query: Free-text query.

        Returns:
            List of technique IDs (e.g. ``["T1059", "T1059.001"]``).
        """
        return _dedupe(_TECHNIQUE_RE.findall(query))

    def extract_cve_ids(self, query: str) -> list[str]:
        """Extract only CVE IDs.

        Args:
            query: Free-text query.

        Returns:
            List of CVE IDs in uppercase (e.g. ``["CVE-2021-44228"]``).
        """
        return _dedupe_upper(_CVE_RE.findall(query))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _dedupe(items: list[str]) -> list[str]:
    """Deduplicate while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _dedupe_upper(items: list[str]) -> list[str]:
    """Uppercase and deduplicate while preserving first-seen order."""
    return _dedupe([i.upper() for i in items])
