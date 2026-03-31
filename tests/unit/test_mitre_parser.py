"""Unit tests for MITRESTIXParser."""

from __future__ import annotations

from seraph.ingestion.mitre_parser import MITRESTIXParser

# ── Minimal STIX fixture ───────────────────────────────────────────────────────

_TACTIC = {
    "id": "x-mitre-tactic--4e57983d-6a41-4c09-8b35-abc5f22a6c01",
    "type": "x-mitre-tactic",
    "name": "Execution",
    "x_mitre_shortname": "execution",
    "description": "Adversaries may run malicious code.",
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "TA0002",
            "url": "https://attack.mitre.org/tactics/TA0002",
        }
    ],
}

_TECHNIQUE = {
    "id": "attack-pattern--7385dfaf-6886-4229-9ecd-6fd678040830",
    "type": "attack-pattern",
    "name": "Command and Scripting Interpreter",
    "description": "Adversaries may abuse scripting interpreters.",
    "x_mitre_is_subtechnique": False,
    "x_mitre_platforms": ["Linux", "Windows", "macOS"],
    "x_mitre_detection": "Monitor process creation.",
    "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "execution"}],
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "T1059",
            "url": "https://attack.mitre.org/techniques/T1059",
        }
    ],
}

_SUBTECHNIQUE = {
    "id": "attack-pattern--a9d4b653-b284-4b8a-a6b1-cd19a8cc4eb0",
    "type": "attack-pattern",
    "name": "PowerShell",
    "description": "Adversaries may abuse PowerShell.",
    "x_mitre_is_subtechnique": True,
    "x_mitre_platforms": ["Windows"],
    "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "execution"}],
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "T1059.001",
            "url": "https://attack.mitre.org/techniques/T1059/001",
        }
    ],
}

_MITIGATION = {
    "id": "course-of-action--2f316f6c-ae42-44f7-8226-dfb6d8e9cca8",
    "type": "course-of-action",
    "name": "Execution Prevention",
    "description": "Block execution of unauthorized code.",
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "M1038",
            "url": "https://attack.mitre.org/mitigations/M1038",
        }
    ],
}

_SOFTWARE = {
    "id": "malware--da5880b4-f7da-4869-85f2-e0aba84b8565",
    "type": "malware",
    "name": "Cobalt Strike",
    "description": "Cobalt Strike is a post-exploitation framework.",
    "x_mitre_platforms": ["Windows"],
    "x_mitre_aliases": ["CS"],
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "S0154",
            "url": "https://attack.mitre.org/software/S0154",
        }
    ],
}

_GROUP = {
    "id": "intrusion-set--4a2ce82e-1a74-468a-a6fb-aa00f5e0a7fc",
    "type": "intrusion-set",
    "name": "APT29",
    "description": "APT29 is a threat group.",
    "aliases": ["Cozy Bear"],
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "G0016",
            "url": "https://attack.mitre.org/groups/G0016",
        }
    ],
}

_DATA_SOURCE = {
    "id": "x-mitre-data-source--d6188aac-17db-4861-845f-57c369f9b4c7",
    "type": "x-mitre-data-source",
    "name": "Process",
    "description": "Information about processes.",
    "external_references": [
        {
            "source_name": "mitre-attack",
            "external_id": "DS0009",
            "url": "https://attack.mitre.org/datasources/DS0009",
        }
    ],
}

_MITIGATES_REL = {
    "id": "relationship--abc123",
    "type": "relationship",
    "relationship_type": "mitigates",
    "source_ref": "course-of-action--2f316f6c-ae42-44f7-8226-dfb6d8e9cca8",
    "target_ref": "attack-pattern--7385dfaf-6886-4229-9ecd-6fd678040830",
    "description": "Prevent execution.",
}

_USES_REL = {
    "id": "relationship--def456",
    "type": "relationship",
    "relationship_type": "uses",
    "source_ref": "intrusion-set--4a2ce82e-1a74-468a-a6fb-aa00f5e0a7fc",
    "target_ref": "attack-pattern--7385dfaf-6886-4229-9ecd-6fd678040830",
    "description": "APT29 uses this technique.",
}

_SUBTECHNIQUE_REL = {
    "id": "relationship--sub123",
    "type": "relationship",
    "relationship_type": "subtechnique-of",
    "source_ref": "attack-pattern--a9d4b653-b284-4b8a-a6b1-cd19a8cc4eb0",
    "target_ref": "attack-pattern--7385dfaf-6886-4229-9ecd-6fd678040830",
}

_REVOKED_TECHNIQUE = {
    "id": "attack-pattern--revoked",
    "type": "attack-pattern",
    "name": "Old Technique",
    "revoked": True,
    "external_references": [{"source_name": "mitre-attack", "external_id": "T9999"}],
}

_DEPRECATED_TECHNIQUE = {
    "id": "attack-pattern--deprecated",
    "type": "attack-pattern",
    "name": "Deprecated Technique",
    "x_mitre_deprecated": True,
    "external_references": [{"source_name": "mitre-attack", "external_id": "T9998"}],
}


def _make_bundle(*objects: dict) -> dict:
    return {"type": "bundle", "spec_version": "2.1", "objects": list(objects)}


class TestMITRESTIXParserTactics:
    def test_parses_tactic(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_TACTIC))
        assert len(bundle.tactics) == 1
        tactic = bundle.tactics[0]
        assert tactic.id == "TA0002"
        assert tactic.name == "Execution"
        assert tactic.shortname == "execution"

    def test_tactic_without_attack_id_skipped(self) -> None:
        parser = MITRESTIXParser()
        obj = {**_TACTIC, "external_references": [{"source_name": "other"}]}
        bundle = parser.parse(_make_bundle(obj))
        assert len(bundle.tactics) == 0


class TestMITRESTIXParserTechniques:
    def test_parses_technique(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_TACTIC, _TECHNIQUE))
        assert len(bundle.techniques) == 1
        tech = bundle.techniques[0]
        assert tech.id == "T1059"
        assert tech.name == "Command and Scripting Interpreter"
        assert not tech.is_subtechnique
        assert "Linux" in tech.platforms

    def test_technique_tactic_ids_from_kill_chain(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_TACTIC, _TECHNIQUE))
        tech = bundle.techniques[0]
        assert "TA0002" in tech.tactic_ids

    def test_subtechnique_detected(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_SUBTECHNIQUE))
        tech = bundle.techniques[0]
        assert tech.is_subtechnique is True
        assert tech.id == "T1059.001"
        assert tech.parent_id == "T1059"

    def test_revoked_skipped(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_REVOKED_TECHNIQUE))
        assert len(bundle.techniques) == 0

    def test_deprecated_skipped(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_DEPRECATED_TECHNIQUE))
        assert len(bundle.techniques) == 0


class TestMITRESTIXParserOtherObjects:
    def test_parses_mitigation(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_MITIGATION))
        assert len(bundle.mitigations) == 1
        assert bundle.mitigations[0].id == "M1038"

    def test_parses_software(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_SOFTWARE))
        assert len(bundle.software) == 1
        sw = bundle.software[0]
        assert sw.id == "S0154"
        assert sw.software_type == "malware"

    def test_parses_group(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_GROUP))
        assert len(bundle.groups) == 1
        assert bundle.groups[0].aliases == ["Cozy Bear"]

    def test_parses_data_source(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_DATA_SOURCE))
        assert len(bundle.data_sources) == 1
        assert bundle.data_sources[0].id == "DS0009"


class TestMITRESTIXParserRelationships:
    def test_parses_mitigates_rel(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_MITIGATION, _TECHNIQUE, _MITIGATES_REL))
        mitigates = [r for r in bundle.relationships if r.rel_type == "MITIGATES"]
        assert len(mitigates) == 1
        assert mitigates[0].source_id == "M1038"
        assert mitigates[0].target_id == "T1059"

    def test_parses_uses_rel(self) -> None:
        parser = MITRESTIXParser()
        bundle = parser.parse(_make_bundle(_GROUP, _TECHNIQUE, _USES_REL))
        uses = [r for r in bundle.relationships if r.rel_type == "USES"]
        assert len(uses) == 1
        assert uses[0].source_id == "G0016"
        assert uses[0].target_id == "T1059"

    def test_unknown_rel_type_skipped(self) -> None:
        parser = MITRESTIXParser()
        unknown_rel = {**_USES_REL, "relationship_type": "has-nothing-to-do-with"}
        bundle = parser.parse(_make_bundle(_GROUP, _TECHNIQUE, unknown_rel))
        assert len(bundle.relationships) == 0

    def test_rel_with_missing_endpoint_skipped(self) -> None:
        parser = MITRESTIXParser()
        rel = {**_MITIGATES_REL, "source_ref": "course-of-action--nonexistent"}
        bundle = parser.parse(_make_bundle(_TECHNIQUE, rel))
        assert len(bundle.relationships) == 0


class TestMITRESTIXParserDerivedRels:
    def test_tactic_technique_rels_from_kill_chain(self) -> None:
        parser = MITRESTIXParser()
        parsed = parser.parse(_make_bundle(_TACTIC, _TECHNIQUE))
        rels = parser.build_tactic_technique_rels(parsed.techniques)
        assert len(rels) == 1
        assert rels[0].rel_type == "USES_TECHNIQUE"
        assert rels[0].source_id == "TA0002"
        assert rels[0].target_id == "T1059"

    def test_subtechnique_rels_built(self) -> None:
        parser = MITRESTIXParser()
        parsed = parser.parse(_make_bundle(_SUBTECHNIQUE))
        rels = parser.build_subtechnique_rels(parsed.techniques)
        assert len(rels) == 1
        assert rels[0].rel_type == "SUBTECHNIQUE_OF"
        assert rels[0].source_id == "T1059.001"
        assert rels[0].target_id == "T1059"

    def test_no_subtechnique_rels_for_parent_techniques(self) -> None:
        parser = MITRESTIXParser()
        parsed = parser.parse(_make_bundle(_TECHNIQUE))
        rels = parser.build_subtechnique_rels(parsed.techniques)
        assert len(rels) == 0
