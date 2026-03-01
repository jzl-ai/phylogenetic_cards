"""Selectors and converters for mapping clades to card content."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from .models import CardBack, CardContent, CardFront, Clade, TaxonomicRank
from .tree import PhylogeneticTree


def clade_to_card(clade: Clade) -> CardContent:
    """Default converter: turn a Clade into flat CardContent."""
    front = CardFront(
        latin_name=clade.latin_name,
        common_name=clade.common_name,
        divergence_mya=clade.divergence_mya,
        rank=clade.rank.value,
    )
    back = CardBack(
        synapomorphies=list(clade.synapomorphies),
        representative_species=[str(sp) for sp in clade.representative_species],
        parent_clade_name=clade.parent.common_name if clade.parent else None,
        child_clade_names=[c.common_name for c in clade.children],
        divergence_mya=clade.divergence_mya,
    )
    return CardContent(clade_id=clade.id, front=front, back=back)


class CardSelector(ABC):
    @abstractmethod
    def select(self, tree: PhylogeneticTree) -> list[Clade]:
        ...


class AllClades(CardSelector):
    def select(self, tree: PhylogeneticTree) -> list[Clade]:
        return list(tree.walk())


class ByRank(CardSelector):
    def __init__(self, rank: TaxonomicRank) -> None:
        self.rank = rank

    def select(self, tree: PhylogeneticTree) -> list[Clade]:
        return tree.clades_by_rank(self.rank)


class ByDepthRange(CardSelector):
    def __init__(self, min_depth: int = 0, max_depth: int = 999) -> None:
        self.min_depth = min_depth
        self.max_depth = max_depth

    def select(self, tree: PhylogeneticTree) -> list[Clade]:
        return [
            c for c in tree.walk()
            if self.min_depth <= c.depth <= self.max_depth
        ]


class HandPicked(CardSelector):
    def __init__(self, clade_ids: list[str]) -> None:
        self.clade_ids = clade_ids

    def select(self, tree: PhylogeneticTree) -> list[Clade]:
        return [tree.get(cid) for cid in self.clade_ids]


class RendezvousPoints(CardSelector):
    def select(self, tree: PhylogeneticTree) -> list[Clade]:
        return [c for c in tree.walk() if c.rendezvous_number is not None]


def generate_card_set(
    tree: PhylogeneticTree,
    selector: CardSelector,
    converter: Callable[[Clade], CardContent] = clade_to_card,
) -> list[CardContent]:
    """Pipeline: select clades from tree, convert each to CardContent."""
    clades = selector.select(tree)
    return [converter(c) for c in clades]
