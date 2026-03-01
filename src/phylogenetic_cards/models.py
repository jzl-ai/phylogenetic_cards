"""Core data models for phylogenetic cards."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


class TaxonomicRank(Enum):
    DOMAIN = "Domain"
    KINGDOM = "Kingdom"
    PHYLUM = "Phylum"
    SUBPHYLUM = "Subphylum"
    SUPERCLASS = "Superclass"
    CLASS = "Class"
    SUBCLASS = "Subclass"
    SUPERORDER = "Superorder"
    ORDER = "Order"
    SUBORDER = "Suborder"
    INFRAORDER = "Infraorder"
    SUPERFAMILY = "Superfamily"
    FAMILY = "Family"
    SUBFAMILY = "Subfamily"
    GENUS = "Genus"
    SPECIES = "Species"
    INFORMAL = "Informal"


@dataclass
class Species:
    latin_name: str
    common_name: str

    def __str__(self) -> str:
        return f"{self.latin_name} ({self.common_name})"


@dataclass
class Clade:
    id: str
    latin_name: str
    common_name: str
    rank: TaxonomicRank
    divergence_mya: float | None = None
    synapomorphies: list[str] = field(default_factory=list)
    representative_species: list[Species] = field(default_factory=list)
    rendezvous_number: int | None = None
    parent: Clade | None = field(default=None, repr=False)
    children: list[Clade] = field(default_factory=list, repr=False)

    def add_child(self, child: Clade) -> None:
        child.parent = self
        self.children.append(child)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    @property
    def depth(self) -> int:
        d = 0
        node = self
        while node.parent is not None:
            d += 1
            node = node.parent
        return d

    def ancestors(self) -> Iterator[Clade]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


@dataclass
class CardFront:
    latin_name: str
    common_name: str
    divergence_mya: float | None
    rank: str


@dataclass
class CardBack:
    synapomorphies: list[str]
    representative_species: list[str]
    parent_clade_name: str | None
    child_clade_names: list[str]
    divergence_mya: float | None


@dataclass
class CardContent:
    clade_id: str
    front: CardFront
    back: CardBack
