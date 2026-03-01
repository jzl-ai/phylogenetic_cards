"""LLM-powered research pipeline for clade character classification via Gemini."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Character, CharacterSystem, CharacterType, Clade, Species


class ResearchCache:
    """Disk-based JSON cache for research results, one file per clade."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, clade_id: str) -> dict | None:
        path = self.cache_dir / f"{clade_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def put(self, clade_id: str, data: dict) -> Path:
        path = self.cache_dir / f"{clade_id}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def has(self, clade_id: str) -> bool:
        return (self.cache_dir / f"{clade_id}.json").exists()


@dataclass
class ResearchResult:
    characters: list[Character]
    representative_species: list[Species]


def build_research_prompt(clade: Clade) -> str:
    """Craft a Gemini prompt for researching characters of a clade."""
    parent_info = ""
    if clade.parent:
        parent_info = (
            f"Parent clade: {clade.parent.latin_name} ({clade.parent.common_name}). "
            f"Characters shared with the parent are plesiomorphies, not synapomorphies."
        )

    children_info = ""
    if clade.children:
        child_names = [f"{c.latin_name} ({c.common_name})" for c in clade.children]
        children_info = f"Child clades: {', '.join(child_names)}."

    rank_info = f"Rank: {clade.rank.value}"
    time_info = ""
    if clade.divergence_mya is not None:
        time_info = f"Divergence time: approximately {clade.divergence_mya} million years ago."

    return f"""You are a systematic biologist. Research the clade {clade.latin_name} ({clade.common_name}).

{rank_info}
{time_info}
{parent_info}
{children_info}

DEFINITIONS:
- SYNAPOMORPHY: A shared derived character that defines THIS clade — present in all (or most) members but NOT in the ancestor before this clade diverged. This is what makes this group a natural group.
- AUTAPOMORPHY: A unique derived character found in only one lineage within this clade — not shared across the whole group.
- PLESIOMORPHY: An ancestral character retained from a more distant ancestor — present in this clade but also in outgroups. Not diagnostic for this clade.

TASK:
1. Identify 4-8 well-supported characters for this clade. Focus on synapomorphies (the most important), but include autapomorphies or plesiomorphies if they are commonly discussed or notable.

2. For each character, classify it as one of: synapomorphy, autapomorphy, plesiomorphy

3. For each character, classify its system as one of: morphological, molecular, behavioral, physiological

4. Choose 3-5 representative species that show the diversity within this clade. Include species from different subgroups to illustrate the range.

Return ONLY valid JSON in this exact format:
{{
  "characters": [
    {{
      "description": "Brief description of the character",
      "character_type": "synapomorphy",
      "system": "morphological",
      "notes": "Optional notes, e.g. 'lost in some derived members'"
    }}
  ],
  "representative_species": [
    {{
      "latin_name": "Genus species",
      "common_name": "Common name"
    }}
  ]
}}"""


def _extract_json(text: str) -> dict:
    """Extract a JSON object from freeform text, stripping markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # Last resort: find first { ... last }
    start = text.index("{")
    end = text.rindex("}") + 1
    return json.loads(text[start:end])


def _parse_research_response(raw: dict) -> ResearchResult:
    """Parse a JSON research response into a ResearchResult."""
    characters = []
    for entry in raw.get("characters", []):
        try:
            ct = CharacterType(entry.get("character_type", "synapomorphy"))
        except ValueError:
            ct = CharacterType.SYNAPOMORPHY
        try:
            cs = CharacterSystem(entry.get("system", "morphological"))
        except ValueError:
            cs = CharacterSystem.MORPHOLOGICAL
        characters.append(Character(
            description=entry["description"],
            character_type=ct,
            system=cs,
            notes=entry.get("notes", ""),
        ))

    species = []
    for sp in raw.get("representative_species", []):
        species.append(Species(
            latin_name=sp["latin_name"],
            common_name=sp["common_name"],
        ))

    return ResearchResult(characters=characters, representative_species=species)


class CladeResearcher:
    """Researches clade characters using Google Gemini with search grounding."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str | Path = "research_cache",
    ) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Google API key required. Set GOOGLE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.cache = ResearchCache(cache_dir)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise ImportError(
                    "google-genai package required for research. "
                    "Install with: pip install 'phylogenetic-cards[artwork]'"
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def research(self, clade: Clade, force: bool = False) -> ResearchResult:
        """Research a single clade. Returns cached result if available."""
        if not force and self.cache.has(clade.id):
            cached = self.cache.get(clade.id)
            return _parse_research_response(cached)

        prompt = build_research_prompt(clade)

        try:
            from google.genai import types

            # NOTE: response_mime_type="application/json" is incompatible with
            # google_search grounding — the API rejects the combination. Instead
            # we ask for JSON in the prompt and parse it from freeform text.
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )

            text = response.text.strip()
            raw = _extract_json(text)

            # Extract grounding sources and report diagnostics
            sources = []
            grounding = (
                response.candidates
                and response.candidates[0].grounding_metadata
            )
            if grounding:
                meta = response.candidates[0].grounding_metadata
                if meta.grounding_chunks:
                    for chunk in meta.grounding_chunks:
                        if chunk.web and chunk.web.uri:
                            sources.append(chunk.web.uri)
                if meta.web_search_queries:
                    print(f"    Search queries: {meta.web_search_queries}")

            if sources:
                print(f"    Grounded with {len(sources)} web source(s)")
            else:
                print(f"    No search grounding (model used training data only)")

            # Build cache entry
            cache_data = {
                "clade_id": clade.id,
                "latin_name": clade.latin_name,
                "common_name": clade.common_name,
                "characters": raw.get("characters", []),
                "representative_species": raw.get("representative_species", []),
                "model": "gemini-2.5-flash",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": sources,
            }
            self.cache.put(clade.id, cache_data)

            return _parse_research_response(raw)

        except Exception as exc:
            print(f"  Warning: research failed for {clade.id}: {exc}")
            # Fall back to existing characters
            return ResearchResult(
                characters=list(clade.characters),
                representative_species=list(clade.representative_species),
            )

    def research_batch(
        self, clades: list[Clade], force: bool = False
    ) -> dict[str, ResearchResult]:
        """Research multiple clades."""
        results: dict[str, ResearchResult] = {}
        for i, clade in enumerate(clades, 1):
            cached = " (cached)" if self.cache.has(clade.id) and not force else ""
            print(f"  [{i}/{len(clades)}] {clade.common_name}{cached}")
            results[clade.id] = self.research(clade, force=force)
        return results
