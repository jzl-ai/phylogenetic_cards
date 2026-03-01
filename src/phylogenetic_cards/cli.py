"""CLI entry point for phylogenetic card generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .card_mapping import (
    AllClades,
    CardSelector,
    RendezvousPoints,
    generate_card_set,
)
from .renderer import CardRenderer
from .tree import PhylogeneticTree


SELECTOR_MAP: dict[str, type[CardSelector]] = {
    "all": AllClades,
    "rendezvous": RendezvousPoints,
}

DEFAULT_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "ancestors_tale.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate printable phylogenetic flash cards",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help="Path to phylogenetic tree YAML file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory for card images",
    )
    parser.add_argument(
        "--selector",
        choices=list(SELECTOR_MAP.keys()),
        default="rendezvous",
        help="Which clades to generate cards for",
    )
    args = parser.parse_args()

    print(f"Loading tree from {args.data}")
    tree = PhylogeneticTree.from_yaml(args.data)

    selector = SELECTOR_MAP[args.selector]()
    cards = generate_card_set(tree, selector)
    print(f"Selected {len(cards)} clades")

    renderer = CardRenderer()
    for card in cards:
        front_path, back_path = renderer.render_to_files(card, args.output)
        print(f"  {card.clade_id}: {front_path.name}, {back_path.name}")

    print(f"Done. {len(cards)} card pairs written to {args.output}/")


if __name__ == "__main__":
    main()
