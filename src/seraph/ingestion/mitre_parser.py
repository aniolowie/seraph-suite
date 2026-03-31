"""MITRE ATT&CK STIX 2.1 bundle parser.

Parses the Enterprise ATT&CK STIX bundle JSON into typed graph model objects.
Does not perform any I/O — takes a pre-loaded dict and returns a
``ParsedSTIXBundle``.

STIX quirks handled:
- Revoked/deprecated objects are skipped.
- Sub-techniques detected by ``x_mitre_is_subtechnique`` flag.
- External references used to derive ATT&CK IDs (T1059, TA0002, etc.).
- ``kill_chain_phases`` used to map techniques to tactic IDs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from seraph.knowledge.graph_models import (
    DataSourceNode,
    GraphRelationship,
    GroupNode,
    MitigationNode,
    ParsedSTIXBundle,
    SoftwareNode,
    TacticNode,
    TechniqueNode,
)

log = structlog.get_logger(__name__)

_CONFIGS_DIR = Path(__file__).parent.parent.parent.parent / "configs"
_MITRE_CONFIG_PATH = _CONFIGS_DIR / "mitre_attack.yaml"

# STIX relationship types we care about
_SUPPORTED_REL_TYPES = {
    "uses",
    "mitigates",
    "subtechnique-of",
    "detects",
    "attributed-to",
}


def _load_mitre_config() -> dict:
    """Load the MITRE ATT&CK YAML config."""
    if _MITRE_CONFIG_PATH.exists():
        with _MITRE_CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _get_attack_id(obj: dict) -> str:
    """Extract the ATT&CK ID (T1059, TA0001, etc.) from external_references."""
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id", "")
    return ""


def _get_url(obj: dict) -> str:
    """Extract the ATT&CK URL from external_references."""
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("url", "")
    return ""


def _is_deprecated(obj: dict) -> bool:
    """Return True if the STIX object is revoked or deprecated."""
    return bool(obj.get("revoked") or obj.get("x_mitre_deprecated"))


class MITRESTIXParser:
    """Parses a MITRE ATT&CK Enterprise STIX 2.1 bundle.

    Args:
        config: Optional override for the MITRE YAML config dict.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialise the parser, loading YAML config."""
        self._config = config or _load_mitre_config()
        self._shortname_to_id: dict[str, str] = self._config.get("tactic_shortname_to_id", {})
        self._rel_type_map: dict[str, str] = self._config.get("relationship_type_map", {})

    def parse(self, bundle: dict) -> ParsedSTIXBundle:
        """Parse a STIX bundle dict into a ``ParsedSTIXBundle``.

        Args:
            bundle: Parsed STIX 2.1 bundle as a Python dict.

        Returns:
            ``ParsedSTIXBundle`` with all extracted objects.
        """
        objects: list[dict] = bundle.get("objects", [])
        version = bundle.get("spec_version", "")

        # Build STIX ID → ATT&CK ID map for relationship resolution
        stix_id_to_attack_id: dict[str, str] = {}
        stix_id_to_label: dict[str, str] = {}
        for obj in objects:
            attack_id = _get_attack_id(obj)
            if attack_id:
                stix_id_to_attack_id[obj["id"]] = attack_id
                stix_id_to_label[obj["id"]] = obj.get("type", "")

        result = ParsedSTIXBundle(stix_version=version)
        skipped = 0

        for obj in objects:
            if _is_deprecated(obj):
                skipped += 1
                continue
            obj_type = obj.get("type", "")
            try:
                if obj_type == "x-mitre-tactic":
                    node = self._parse_tactic(obj)
                    if node:
                        result.tactics.append(node)
                elif obj_type == "attack-pattern":
                    node = self._parse_technique(obj)
                    if node:
                        result.techniques.append(node)
                elif obj_type == "course-of-action":
                    node = self._parse_mitigation(obj)
                    if node:
                        result.mitigations.append(node)
                elif obj_type in ("malware", "tool"):
                    node = self._parse_software(obj)
                    if node:
                        result.software.append(node)
                elif obj_type == "intrusion-set":
                    node = self._parse_group(obj)
                    if node:
                        result.groups.append(node)
                elif obj_type == "x-mitre-data-source":
                    node = self._parse_data_source(obj)
                    if node:
                        result.data_sources.append(node)
                elif obj_type == "relationship":
                    rels = self._parse_relationship(obj, stix_id_to_attack_id, stix_id_to_label)
                    result.relationships.extend(rels)
            except Exception:
                log.warning(
                    "mitre_parser.skip_object",
                    obj_type=obj_type,
                    obj_id=obj.get("id", ""),
                )

        log.info(
            "mitre_parser.parsed",
            tactics=len(result.tactics),
            techniques=len(result.techniques),
            mitigations=len(result.mitigations),
            software=len(result.software),
            groups=len(result.groups),
            relationships=len(result.relationships),
            skipped=skipped,
        )
        return result

    # ── Object parsers ────────────────────────────────────────────────────────

    def _parse_tactic(self, obj: dict) -> TacticNode | None:
        """Parse a ``x-mitre-tactic`` object."""
        attack_id = _get_attack_id(obj)
        if not attack_id:
            return None
        return TacticNode(
            id=attack_id,
            name=obj.get("name", ""),
            description=obj.get("description", ""),
            url=_get_url(obj),
            shortname=obj.get("x_mitre_shortname", ""),
        )

    def _parse_technique(self, obj: dict) -> TechniqueNode | None:
        """Parse an ``attack-pattern`` object."""
        attack_id = _get_attack_id(obj)
        if not attack_id:
            return None
        is_sub = bool(obj.get("x_mitre_is_subtechnique", False))
        parent_id = ""
        if is_sub and "." in attack_id:
            parent_id = attack_id.split(".")[0]

        # Map kill_chain_phases to tactic IDs
        tactic_ids: list[str] = []
        for phase in obj.get("kill_chain_phases", []):
            shortname = phase.get("phase_name", "")
            tactic_id = self._shortname_to_id.get(shortname, "")
            if tactic_id:
                tactic_ids.append(tactic_id)

        platforms: list[str] = obj.get("x_mitre_platforms", [])

        return TechniqueNode(
            id=attack_id,
            name=obj.get("name", ""),
            description=obj.get("description", ""),
            url=_get_url(obj),
            platforms=platforms,
            detection=obj.get("x_mitre_detection", ""),
            is_subtechnique=is_sub,
            parent_id=parent_id,
            tactic_ids=tactic_ids,
        )

    def _parse_mitigation(self, obj: dict) -> MitigationNode | None:
        """Parse a ``course-of-action`` object."""
        attack_id = _get_attack_id(obj)
        if not attack_id:
            return None
        return MitigationNode(
            id=attack_id,
            name=obj.get("name", ""),
            description=obj.get("description", ""),
            url=_get_url(obj),
        )

    def _parse_software(self, obj: dict) -> SoftwareNode | None:
        """Parse a ``malware`` or ``tool`` object."""
        attack_id = _get_attack_id(obj)
        if not attack_id:
            return None
        return SoftwareNode(
            id=attack_id,
            name=obj.get("name", ""),
            description=obj.get("description", ""),
            url=_get_url(obj),
            software_type=obj.get("type", ""),
            platforms=obj.get("x_mitre_platforms", []),
            aliases=obj.get("x_mitre_aliases", []),
        )

    def _parse_group(self, obj: dict) -> GroupNode | None:
        """Parse an ``intrusion-set`` object."""
        attack_id = _get_attack_id(obj)
        if not attack_id:
            return None
        return GroupNode(
            id=attack_id,
            name=obj.get("name", ""),
            description=obj.get("description", ""),
            url=_get_url(obj),
            aliases=obj.get("aliases", []),
        )

    def _parse_data_source(self, obj: dict) -> DataSourceNode | None:
        """Parse an ``x-mitre-data-source`` object."""
        attack_id = _get_attack_id(obj)
        if not attack_id:
            return None
        return DataSourceNode(
            id=attack_id,
            name=obj.get("name", ""),
            description=obj.get("description", ""),
        )

    def _parse_relationship(
        self,
        obj: dict,
        stix_id_to_attack_id: dict[str, str],
        stix_id_to_label: dict[str, str],
    ) -> list[GraphRelationship]:
        """Parse a STIX ``relationship`` object into graph edges."""
        rel_type_stix = obj.get("relationship_type", "")
        if rel_type_stix not in _SUPPORTED_REL_TYPES:
            return []

        src_stix = obj.get("source_ref", "")
        tgt_stix = obj.get("target_ref", "")
        src_id = stix_id_to_attack_id.get(src_stix, "")
        tgt_id = stix_id_to_attack_id.get(tgt_stix, "")
        if not src_id or not tgt_id:
            return []

        src_type = stix_id_to_label.get(src_stix, "")
        tgt_type = stix_id_to_label.get(tgt_stix, "")
        src_label = self._stix_type_to_label(src_type)
        tgt_label = self._stix_type_to_label(tgt_type)
        if not src_label or not tgt_label:
            return []

        graph_rel_type = self._rel_type_map.get(rel_type_stix, rel_type_stix.upper())
        rels: list[GraphRelationship] = [
            GraphRelationship(
                rel_type=graph_rel_type,
                source_label=src_label,
                source_id=src_id,
                target_label=tgt_label,
                target_id=tgt_id,
                properties={"description": obj.get("description", "")},
            )
        ]

        # For techniques: also create USES_TECHNIQUE from each tactic
        # (derived from kill_chain_phases on the technique, not STIX rels)
        return rels

    @staticmethod
    def _stix_type_to_label(stix_type: str) -> str:
        """Map a STIX object type to a Neo4j label."""
        mapping = {
            "attack-pattern": "Technique",
            "x-mitre-tactic": "Tactic",
            "course-of-action": "Mitigation",
            "malware": "Software",
            "tool": "Software",
            "intrusion-set": "Group",
            "x-mitre-data-source": "DataSource",
            "campaign": "Campaign",
        }
        return mapping.get(stix_type, "")

    def build_tactic_technique_rels(
        self, techniques: list[TechniqueNode]
    ) -> list[GraphRelationship]:
        """Generate USES_TECHNIQUE edges from technique.tactic_ids.

        These relationships are not explicit in STIX — they are derived from
        ``kill_chain_phases`` on each technique.

        Args:
            techniques: Parsed technique nodes with ``tactic_ids`` populated.

        Returns:
            List of ``GraphRelationship`` with type ``USES_TECHNIQUE``.
        """
        rels: list[GraphRelationship] = []
        for tech in techniques:
            for tactic_id in tech.tactic_ids:
                rels.append(
                    GraphRelationship(
                        rel_type="USES_TECHNIQUE",
                        source_label="Tactic",
                        source_id=tactic_id,
                        target_label="Technique",
                        target_id=tech.id,
                    )
                )
        return rels

    def build_subtechnique_rels(self, techniques: list[TechniqueNode]) -> list[GraphRelationship]:
        """Generate SUBTECHNIQUE_OF edges from technique.parent_id.

        Args:
            techniques: Parsed technique nodes.

        Returns:
            List of ``GraphRelationship`` with type ``SUBTECHNIQUE_OF``.
        """
        return [
            GraphRelationship(
                rel_type="SUBTECHNIQUE_OF",
                source_label="Technique",
                source_id=tech.id,
                target_label="Technique",
                target_id=tech.parent_id,
            )
            for tech in techniques
            if tech.is_subtechnique and tech.parent_id
        ]


def _node_to_dict(node: Any) -> dict:
    """Convert a Pydantic node model to a plain dict for Neo4j batch upsert."""
    return node.model_dump()
