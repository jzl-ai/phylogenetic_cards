"""Phylogenetic tree loader and query helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import yaml

from .models import Character, CharacterSystem, CharacterType, Clade, Species, TaxonomicRank


class PhylogeneticTree:
    def __init__(self, root: Clade) -> None:
        self.root = root
        self._index: dict[str, Clade] = {}
        self._build_index(root)

    def _build_index(self, node: Clade) -> None:
        self._index[node.id] = node
        for child in node.children:
            self._build_index(child)

    @classmethod
    def from_yaml(cls, path: str | Path) -> PhylogeneticTree:
        with open(path) as f:
            data = yaml.safe_load(f)
        root = cls._parse_node(data)
        return cls(root)

    @classmethod
    def _parse_node(cls, data: dict, parent: Clade | None = None) -> Clade:
        species = []
        for sp in data.get("representative_species", []):
            species.append(Species(
                latin_name=sp["latin_name"],
                common_name=sp["common_name"],
            ))

        rank_str = data.get("rank", "Informal")
        try:
            rank = TaxonomicRank(rank_str)
        except ValueError:
            rank = TaxonomicRank.INFORMAL

        characters = cls._parse_characters(data)

        node = Clade(
            id=data["id"],
            latin_name=data.get("latin_name", ""),
            common_name=data.get("common_name", ""),
            rank=rank,
            divergence_mya=data.get("divergence_mya"),
            characters=characters,
            representative_species=species,
            rendezvous_number=data.get("rendezvous_number"),
            parent=parent,
        )

        for child_data in data.get("children", []):
            child = cls._parse_node(child_data, parent=node)
            node.children.append(child)

        return node

    @staticmethod
    def _parse_characters(data: dict) -> list[Character]:
        """Parse characters from YAML, supporting both old and new formats."""
        # New format: characters: list of dicts
        if "characters" in data:
            chars = []
            for entry in data["characters"]:
                try:
                    ct = CharacterType(entry.get("character_type", "synapomorphy"))
                except ValueError:
                    ct = CharacterType.SYNAPOMORPHY
                try:
                    cs = CharacterSystem(entry.get("system", "morphological"))
                except ValueError:
                    cs = CharacterSystem.MORPHOLOGICAL
                chars.append(Character(
                    description=entry["description"],
                    character_type=ct,
                    system=cs,
                    notes=entry.get("notes", ""),
                ))
            return chars

        # Old format: synapomorphies: list of strings
        if "synapomorphies" in data:
            return [
                Character(
                    description=s,
                    character_type=CharacterType.SYNAPOMORPHY,
                )
                for s in data["synapomorphies"]
            ]

        return []

    def walk(self) -> Iterator[Clade]:
        """Pre-order traversal of all clades."""
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            # Push children in reverse so leftmost is yielded first
            stack.extend(reversed(node.children))

    def get(self, clade_id: str) -> Clade:
        """O(1) lookup by clade id."""
        return self._index[clade_id]

    def clades_at_depth(self, depth: int) -> list[Clade]:
        return [c for c in self.walk() if c.depth == depth]

    def clades_by_rank(self, rank: TaxonomicRank) -> list[Clade]:
        return [c for c in self.walk() if c.rank == rank]
