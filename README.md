# Phylogenetic Cards

Generate printable phylogenetic flash cards from tree data. Each card focuses on a clade (not individual species), with data sourced from Dawkins' *The Ancestor's Tale*.

Cards target Ivory Graphics Large Tarot size (89x127mm, 1051x1500px at 300 DPI) on 310gsm black-cored card stock.

## Installation

```bash
# Core (card rendering only)
pip install -e .

# With AI features (artwork generation + clade research)
pip install -e ".[artwork]"
```

Requires Python 3.11+.

## Quick start

```bash
# Render cards using built-in tree data
phylo-cards --output output/
```

This loads the phylogenetic tree from `data/ancestors_tale.yaml`, selects rendezvous-point clades, and renders front/back card images to `output/`.

## CLI options

```
phylo-cards [OPTIONS]

Selection:
  --data PATH              Path to YAML tree file (default: built-in ancestors_tale.yaml)
  --output PATH            Output directory for card images (default: output/)
  --selector {all,rendezvous}  Which clades to generate cards for (default: rendezvous)

Research (requires GOOGLE_API_KEY):
  --research               Research clade characters via Gemini API
  --force-research         Regenerate research even if cached
  --research-cache PATH    Directory for cached research JSON (default: research_cache/)

Artwork (requires GOOGLE_API_KEY):
  --generate-artwork       Generate AI illustrations via Gemini API
  --force-artwork          Regenerate artwork even if cached
  --artwork-cache PATH     Directory for cached artwork PNGs (default: artwork_cache/)

Rendering:
  --no-tree-diagram        Skip mini tree diagrams on front cards
```

## Pipeline

The full pipeline runs in three phases: **research -> artwork -> render**.

### 1. Render only (no API key needed)

```bash
phylo-cards --output output/
```

Uses characters and species from the YAML file. Cards render without illustrations.

### 2. With AI-generated artwork

```bash
export GOOGLE_API_KEY=your-key-here
phylo-cards --generate-artwork --output output/
```

Generates scientific illustrations via Gemini and caches them in `artwork_cache/`. Subsequent runs reuse cached images unless `--force-artwork` is passed.

### 3. With research + artwork (full pipeline)

```bash
export GOOGLE_API_KEY=your-key-here
phylo-cards --research --generate-artwork --output output/
```

For each clade, the research phase calls Gemini 2.5 Flash with Google Search grounding to identify and classify characters (synapomorphies, autapomorphies, plesiomorphies) with proper biological system labels. Results are cached as JSON in `research_cache/` and merged into the clade data before artwork and card rendering.

Research diagnostics are printed showing whether search grounding was used and how many web sources were cited.

### 4. Research only (no card rendering)

```bash
export GOOGLE_API_KEY=your-key-here
phylo-cards --research --output /dev/null
```

## Data model

Each clade carries structured **characters** rather than flat strings:

- **Character type**: `synapomorphy` (shared derived, defines the clade), `autapomorphy` (unique to one lineage), `plesiomorphy` (ancestral/retained)
- **System**: `morphological`, `molecular`, `behavioral`, `physiological`

Card backs display synapomorphies under a green "SYNAPOMORPHIES" heading, with other character types in a separate "OTHER CHARACTERS" section when present.

## Tree data

The built-in `data/ancestors_tale.yaml` contains ~40 rendezvous points from Eukaryota (2000 MYA) through Hominini (7 MYA), following the path from ancient clades to modern humans. Each node includes characters, representative species, taxonomic rank, and divergence time.

## Project structure

```
src/phylogenetic_cards/
  models.py         Data models (Clade, Character, CardContent, etc.)
  tree.py           YAML tree loader with O(1) clade lookup
  card_mapping.py   Clade selectors and clade-to-card conversion
  renderer.py       Pillow-based card image renderer
  tree_diagram.py   Mini cladogram generator for card fronts
  artwork.py        Gemini image generation with disk caching
  researcher.py     Gemini research pipeline with search grounding
  cli.py            CLI entry point
data/
  ancestors_tale.yaml   Built-in phylogenetic tree
```
