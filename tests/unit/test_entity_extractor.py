"""Unit tests for EntityExtractor."""

from __future__ import annotations

from seraph.knowledge.entity_extractor import EntityExtractor


class TestEntityExtractorCVE:
    def test_extracts_cve_id(self) -> None:
        e = EntityExtractor()
        result = e.extract("Exploiting CVE-2021-44228 in Log4j")
        assert result.cve_ids == ["CVE-2021-44228"]

    def test_extracts_multiple_cves(self) -> None:
        e = EntityExtractor()
        result = e.extract("CVE-2021-44228 and CVE-2022-22965 are both critical")
        assert "CVE-2021-44228" in result.cve_ids
        assert "CVE-2022-22965" in result.cve_ids
        assert len(result.cve_ids) == 2

    def test_cve_normalised_to_uppercase(self) -> None:
        e = EntityExtractor()
        result = e.extract("cve-2021-44228")
        assert result.cve_ids == ["CVE-2021-44228"]

    def test_cve_deduped(self) -> None:
        e = EntityExtractor()
        result = e.extract("CVE-2021-44228 CVE-2021-44228")
        assert result.cve_ids == ["CVE-2021-44228"]

    def test_partial_cve_not_matched(self) -> None:
        e = EntityExtractor()
        result = e.extract("XCVE-2021-44228")  # not at word boundary
        assert result.cve_ids == []

    def test_short_sequence_not_matched(self) -> None:
        # CVE requires 4+ digit sequence
        e = EntityExtractor()
        result = e.extract("CVE-2021-123")
        assert result.cve_ids == []


class TestEntityExtractorTechniques:
    def test_extracts_technique_id(self) -> None:
        e = EntityExtractor()
        result = e.extract("Used T1059 for execution")
        assert result.technique_ids == ["T1059"]

    def test_extracts_subtechnique_id(self) -> None:
        e = EntityExtractor()
        result = e.extract("T1059.001 PowerShell abuse")
        assert result.technique_ids == ["T1059.001"]

    def test_extracts_multiple_techniques(self) -> None:
        e = EntityExtractor()
        result = e.extract("Techniques T1190 and T1068 were used")
        assert "T1190" in result.technique_ids
        assert "T1068" in result.technique_ids

    def test_technique_deduped(self) -> None:
        e = EntityExtractor()
        result = e.extract("T1059 then T1059 again")
        assert result.technique_ids == ["T1059"]

    def test_short_technique_not_matched(self) -> None:
        # Must be exactly 4 digits
        e = EntityExtractor()
        result = e.extract("T105 is not a valid technique")
        assert result.technique_ids == []


class TestEntityExtractorTactics:
    def test_extracts_tactic_id(self) -> None:
        e = EntityExtractor()
        result = e.extract("Initial access via TA0001")
        assert result.tactic_ids == ["TA0001"]

    def test_extracts_multiple_tactics(self) -> None:
        e = EntityExtractor()
        result = e.extract("TA0001 and TA0002 were observed")
        assert len(result.tactic_ids) == 2

    def test_tactic_deduped(self) -> None:
        e = EntityExtractor()
        result = e.extract("TA0002 TA0002")
        assert result.tactic_ids == ["TA0002"]


class TestEntityExtractorCWE:
    def test_extracts_cwe_id(self) -> None:
        e = EntityExtractor()
        result = e.extract("Exploited CWE-79 in the web app")
        assert result.cwe_ids == ["CWE-79"]

    def test_cwe_normalised_to_uppercase(self) -> None:
        e = EntityExtractor()
        result = e.extract("cwe-89 SQL injection")
        assert result.cwe_ids == ["CWE-89"]

    def test_extracts_multiple_cwes(self) -> None:
        e = EntityExtractor()
        result = e.extract("CWE-79 and CWE-89 present")
        assert len(result.cwe_ids) == 2


class TestEntityExtractorMixed:
    def test_mixed_query(self) -> None:
        e = EntityExtractor()
        result = e.extract("CVE-2021-44228 exploited via T1190, tactic TA0001, weakness CWE-502")
        assert result.cve_ids == ["CVE-2021-44228"]
        assert result.technique_ids == ["T1190"]
        assert result.tactic_ids == ["TA0001"]
        assert result.cwe_ids == ["CWE-502"]

    def test_empty_query_returns_no_entities(self) -> None:
        e = EntityExtractor()
        result = e.extract("")
        assert not result.has_entities

    def test_prose_query_returns_no_entities(self) -> None:
        e = EntityExtractor()
        result = e.extract("How do I scan for open ports on a Linux system?")
        assert not result.has_entities

    def test_has_entities_true_with_cve(self) -> None:
        e = EntityExtractor()
        result = e.extract("CVE-2021-44228")
        assert result.has_entities

    def test_all_ids_flat_list(self) -> None:
        e = EntityExtractor()
        result = e.extract("CVE-2021-44228 T1059 TA0002 CWE-79")
        assert len(result.all_ids) == 4
