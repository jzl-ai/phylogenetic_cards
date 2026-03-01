"""AI-generated organism illustrations via Google Gemini API (Nano Banana)."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from .models import Clade


class ArtworkCache:
    """Disk-based cache for generated artwork, keyed by clade_id."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, clade_id: str) -> Path | None:
        path = self.cache_dir / f"{clade_id}.png"
        return path if path.exists() else None

    def put(self, clade_id: str, image: Image.Image) -> Path:
        path = self.cache_dir / f"{clade_id}.png"
        image.save(str(path))
        return path

    def has(self, clade_id: str) -> bool:
        return (self.cache_dir / f"{clade_id}.png").exists()

    def get_detail(self, clade_id: str) -> Path | None:
        path = self.cache_dir / f"{clade_id}_detail.png"
        return path if path.exists() else None

    def put_detail(self, clade_id: str, image: Image.Image) -> Path:
        path = self.cache_dir / f"{clade_id}_detail.png"
        image.save(str(path))
        return path

    def has_detail(self, clade_id: str) -> bool:
        return (self.cache_dir / f"{clade_id}_detail.png").exists()


def build_illustration_prompt(clade: Clade) -> str:
    """Craft a Gemini prompt for a scientific illustration of this clade."""
    if clade.representative_species:
        subject = clade.representative_species[0]
        organism = f"{subject.common_name} ({subject.latin_name})"
    else:
        organism = f"a representative {clade.common_name}"

    features = ""
    if clade.synapomorphies:
        top_features = [c.description for c in clade.synapomorphies[:3]]
        features = "Key features to emphasize: " + ", ".join(top_features) + "."

    return (
        f"Create a detailed naturalistic scientific illustration of {organism}, "
        f"representative of the clade {clade.latin_name} ({clade.common_name}). "
        f"Style: vintage natural history illustration, detailed pen-and-ink with "
        f"subtle watercolor washes, white background, single organism "
        f"centered in frame. {features} "
        f"No text, labels, or annotations in the image."
    )


def build_detail_prompt(clade: Clade) -> str | None:
    """Craft a prompt for a smaller detail illustration. Returns None if not applicable."""
    latin_name = clade.latin_name
    common_name = clade.common_name

    if len(clade.representative_species) >= 2:
        second = clade.representative_species[1]
        first = clade.representative_species[0]
        subject = (
            f"a {second.common_name} ({second.latin_name}), showing how it "
            f"differs from {first.common_name} within this clade"
        )
    elif clade.synapomorphies:
        top_syn = clade.synapomorphies[0].description
        subject = f"an anatomical close-up of {top_syn}"
    else:
        return None

    return (
        f"Create a compact scientific detail illustration for a phylogenetic card "
        f"about {latin_name} ({common_name}). Subject: {subject}. "
        f"Style: vintage natural history illustration, detailed pen-and-ink with "
        f"subtle watercolor washes, white background. Keep the composition simple "
        f"and focused on a single subject. "
        f"No text, labels, or annotations in the image."
    )


class ArtworkGenerator:
    """Generates organism illustrations using Google Gemini API."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str | Path = "artwork_cache",
    ) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Google API key required. Set GOOGLE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.cache = ArtworkCache(cache_dir)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise ImportError(
                    "google-genai package required for artwork generation. "
                    "Install with: pip install 'phylogenetic-cards[artwork]'"
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate_image(self, prompt: str) -> Image.Image | None:
        """Call the Gemini API and return the first image, or None."""
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    return part.as_image()

            return None

        except Exception as exc:
            print(f"  Warning: image generation failed: {exc}")
            return None

    def generate(self, clade: Clade, force: bool = False) -> Path | None:
        """Generate illustration for a clade. Returns path or None on failure."""
        if not force and self.cache.has(clade.id):
            return self.cache.get(clade.id)

        prompt = build_illustration_prompt(clade)
        image = self._generate_image(prompt)
        if image is not None:
            return self.cache.put(clade.id, image)

        print(f"  Warning: no image returned for {clade.id}")
        return None

    def generate_detail(self, clade: Clade, force: bool = False) -> Path | None:
        """Generate detail illustration for a clade. Returns path or None."""
        if not force and self.cache.has_detail(clade.id):
            return self.cache.get_detail(clade.id)

        prompt = build_detail_prompt(clade)
        if prompt is None:
            return None

        image = self._generate_image(prompt)
        if image is not None:
            return self.cache.put_detail(clade.id, image)

        print(f"  Warning: no detail image returned for {clade.id}")
        return None

    def generate_batch(
        self, clades: list[Clade], force: bool = False
    ) -> dict[str, tuple[Path | None, Path | None]]:
        """Generate main + detail illustrations for multiple clades."""
        results: dict[str, tuple[Path | None, Path | None]] = {}
        for i, clade in enumerate(clades, 1):
            cached = " (cached)" if self.cache.has(clade.id) and not force else ""
            print(f"  [{i}/{len(clades)}] {clade.common_name}{cached}")
            main_path = self.generate(clade, force=force)
            detail_path = self.generate_detail(clade, force=force)
            results[clade.id] = (main_path, detail_path)
        return results
