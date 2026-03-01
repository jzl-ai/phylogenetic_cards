"""CLI entry point for phylogenetic card generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from .card_mapping import (
    AllClades,
    CardSelector,
    RendezvousPoints,
    generate_card_set,
)
from .renderer import CardRenderer
from .tree import PhylogeneticTree
from .tree_diagram import TreeDiagramRenderer


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
    parser.add_argument(
        "--research",
        action="store_true",
        default=False,
        help="Research clade characters via Gemini API (requires GOOGLE_API_KEY)",
    )
    parser.add_argument(
        "--force-research",
        action="store_true",
        default=False,
        help="Regenerate research even if cached",
    )
    parser.add_argument(
        "--research-cache",
        type=Path,
        default=Path("research_cache"),
        help="Directory for cached research results",
    )
    parser.add_argument(
        "--generate-artwork",
        action="store_true",
        default=False,
        help="Generate AI illustrations via Gemini API (requires GOOGLE_API_KEY)",
    )
    parser.add_argument(
        "--force-artwork",
        action="store_true",
        default=False,
        help="Regenerate artwork even if cached",
    )
    parser.add_argument(
        "--artwork-cache",
        type=Path,
        default=Path("artwork_cache"),
        help="Directory for cached AI-generated artwork",
    )
    parser.add_argument(
        "--no-tree-diagram",
        action="store_true",
        default=False,
        help="Skip rendering mini tree diagrams on front cards",
    )
    args = parser.parse_args()

    print(f"Loading tree from {args.data}")
    tree = PhylogeneticTree.from_yaml(args.data)

    selector = SELECTOR_MAP[args.selector]()
    pairs = generate_card_set(tree, selector)
    print(f"Selected {len(pairs)} clades")

    # Phase 1: Research (optional)
    if args.research:
        from .researcher import CladeResearcher

        print("Researching clade characters...")
        researcher = CladeResearcher(cache_dir=args.research_cache)
        research_results = researcher.research_batch(
            [clade for clade, _ in pairs],
            force=args.force_research,
        )

        # Merge research results into Clade objects
        for clade, _ in pairs:
            result = research_results.get(clade.id)
            if result:
                clade.characters = result.characters
                clade.representative_species = result.representative_species

        # Re-generate card content with updated clade data
        from .card_mapping import clade_to_card

        pairs = [(clade, clade_to_card(clade)) for clade, _ in pairs]

    # Phase 2: Artwork generation / loading
    artwork_map: dict[str, Path | None] = {}
    if args.generate_artwork:
        from .artwork import ArtworkGenerator

        print("Generating AI artwork...")
        generator = ArtworkGenerator(cache_dir=args.artwork_cache)
        artwork_map = generator.generate_batch(
            [clade for clade, _ in pairs],
            force=args.force_artwork,
        )
    else:
        # Check cache for pre-existing artwork
        from .artwork import ArtworkCache

        cache = ArtworkCache(args.artwork_cache)
        for clade, _ in pairs:
            artwork_map[clade.id] = cache.get(clade.id)

    # Phase 3: Render cards
    renderer = CardRenderer()
    tree_renderer = None if args.no_tree_diagram else TreeDiagramRenderer()

    for clade, card in pairs:
        # Load illustration if available
        illustration = None
        art_path = artwork_map.get(clade.id)
        if art_path is not None:
            illustration = Image.open(art_path)

        # Render tree diagram
        tree_diagram = None
        if tree_renderer is not None:
            tree_diagram = tree_renderer.render(clade)

        front_path, back_path = renderer.render_to_files(
            card, args.output,
            illustration=illustration,
            tree_diagram=tree_diagram,
        )
        print(f"  {card.clade_id}: {front_path.name}, {back_path.name}")

    print(f"Done. {len(pairs)} card pairs written to {args.output}/")


if __name__ == "__main__":
    main()
