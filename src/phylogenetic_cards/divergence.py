"""TimeTree divergence time resolver for phylogenetic clades."""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from .models import Clade


class DivergenceCache:
    """Disk-based JSON cache for divergence time lookups, one file per clade."""

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

    def load_batch(self, clade_ids: list[str]) -> dict[str, float | None]:
        """Read cached divergence times for a list of clade IDs.

        Returns a dict mapping clade_id -> divergence_mya (or None if not cached).
        """
        results: dict[str, float | None] = {}
        for clade_id in clade_ids:
            entry = self.get(clade_id)
            if entry is not None:
                results[clade_id] = entry.get("divergence_mya")
            else:
                results[clade_id] = None
        return results


class DivergenceResolver:
    """Resolves clade divergence times via TimeTree taxon lookup + pairwise API."""

    # timetree.org/api/taxon/ works for name→ID lookups (returns JSON)
    # timetree.temple.edu/api/pairwise/ works for divergence times (returns CSV)
    TAXON_URL = "http://timetree.org/api/taxon/{name}"
    PAIRWISE_URL = "http://timetree.temple.edu/api/pairwise/{id1}/{id2}"

    def __init__(self, cache_dir: str | Path = "divergence_cache") -> None:
        self.cache = DivergenceCache(cache_dir)
        self._ncbi_ids: dict[str, int | None] = {}
        self._ncbi_cache_path = self.cache.cache_dir / "_ncbi_ids.json"
        self._load_ncbi_cache()
        # Unverified SSL context for TimeTree (expired certificate)
        self._timetree_ssl = ssl._create_unverified_context()

    def _load_ncbi_cache(self) -> None:
        """Load persisted NCBI ID mappings from disk."""
        if self._ncbi_cache_path.exists():
            with open(self._ncbi_cache_path) as f:
                data = json.load(f)
            # JSON keys are strings; values may be int or None
            self._ncbi_ids = {k: v for k, v in data.items()}

    def _save_ncbi_cache(self) -> None:
        """Persist NCBI ID mappings to disk."""
        with open(self._ncbi_cache_path, "w") as f:
            json.dump(self._ncbi_ids, f, indent=2)

    def resolve(self, clade: Clade, force: bool = False) -> float | None:
        """Look up divergence time for a clade. Returns MYA or None."""
        if not force and self.cache.has(clade.id):
            cached = self.cache.get(clade.id)
            if cached is not None:
                return cached.get("divergence_mya")

        # Pick ingroup species
        if not clade.representative_species:
            print(f"    No representative species for {clade.id}, skipping")
            return None
        ingroup = clade.representative_species[0].latin_name

        # Pick outgroup species candidates
        outgroup = self._find_outgroup_species(clade)
        if not outgroup:
            print(f"    No outgroup species found for {clade.id}, skipping")
            return None

        # Look up NCBI taxonomy IDs
        ingroup_ncbi = self._lookup_ncbi_id(ingroup)
        if ingroup_ncbi is None:
            print(f"    Could not resolve NCBI ID for ingroup {ingroup}")
            return None

        # Try each outgroup candidate until one resolves
        outgroup_ncbi = None
        for candidate in outgroup:
            outgroup_ncbi = self._lookup_ncbi_id(candidate)
            if outgroup_ncbi is not None:
                outgroup = candidate
                break
        else:
            outgroup = outgroup[-1]  # for cache record

        if outgroup_ncbi is None:
            print(f"    Could not resolve NCBI ID for any outgroup candidate")
            return None

        # Query TimeTree
        mya = self._query_timetree(ingroup_ncbi, outgroup_ncbi)

        # Cache result regardless of success
        cache_data = {
            "clade_id": clade.id,
            "ingroup_species": ingroup,
            "outgroup_species": outgroup,
            "ingroup_ncbi_id": ingroup_ncbi,
            "outgroup_ncbi_id": outgroup_ncbi,
            "divergence_mya": mya,
            "source": "timetree.org",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        self.cache.put(clade.id, cache_data)
        self._save_ncbi_cache()

        return mya

    def resolve_batch(
        self, clades: list[Clade], force: bool = False
    ) -> dict[str, float | None]:
        """Resolve divergence times for multiple clades."""
        results: dict[str, float | None] = {}
        for i, clade in enumerate(clades, 1):
            cached = " (cached)" if self.cache.has(clade.id) and not force else ""
            print(f"  [{i}/{len(clades)}] {clade.common_name}{cached}")
            results[clade.id] = self.resolve(clade, force=force)
        return results

    def _find_outgroup_species(self, clade: Clade) -> list[str]:
        """Walk siblings -> parent -> ancestors to collect outgroup species candidates.

        Returns a list of latin names, ordered by preference (closest relatives first).
        Multiple candidates are returned so the caller can skip extinct species
        that aren't in TimeTree.
        """
        candidates: list[str] = []
        seen: set[str] = set()
        parent = clade.parent
        if parent is None:
            return candidates

        def _add(species_list: list) -> None:
            for sp in species_list:
                if sp.latin_name not in seen:
                    seen.add(sp.latin_name)
                    candidates.append(sp.latin_name)

        # 1. Check sibling clades (other children of parent)
        for sibling in parent.children:
            if sibling.id == clade.id:
                continue
            _add(sibling.representative_species)

        # 2. Check parent's own representative species
        _add(parent.representative_species)

        # 3. Walk up ancestors
        prev = parent
        for ancestor in parent.ancestors():
            # Check ancestor's children (aunts/uncles) for species
            for child in ancestor.children:
                if child.id == prev.id:
                    continue
                _add(child.representative_species)
            # Check ancestor's own species
            _add(ancestor.representative_species)
            prev = ancestor

        return candidates

    def _lookup_ncbi_id(self, latin_name: str) -> int | None:
        """Look up NCBI taxonomy ID via TimeTree's taxon endpoint."""
        if latin_name in self._ncbi_ids:
            return self._ncbi_ids[latin_name]

        url = self.TAXON_URL.format(name=urllib.request.quote(latin_name))

        try:
            time.sleep(0.5)  # Rate limit
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "phylogenetic-cards/1.0")
            with urllib.request.urlopen(req, timeout=15, context=self._timetree_ssl) as resp:
                data = json.loads(resp.read().decode())
            ncbi_id = data.get("ncbi_id") or data.get("taxon_id")
            if ncbi_id is not None:
                ncbi_id = int(ncbi_id)
                self._ncbi_ids[latin_name] = ncbi_id
                return ncbi_id
            else:
                print(f"    TimeTree returned no taxon ID for '{latin_name}'")
                self._ncbi_ids[latin_name] = None
                return None
        except (urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            print(f"    Warning: taxon lookup failed for '{latin_name}': {exc}")
            self._ncbi_ids[latin_name] = None
            return None

    def _query_timetree(self, ncbi_id_1: int, ncbi_id_2: int) -> float | None:
        """Query TimeTree pairwise API for divergence time in MYA.

        Uses timetree.temple.edu which returns CSV:
          header row + data row with precomputed_age column.
        """
        url = self.PAIRWISE_URL.format(id1=ncbi_id_1, id2=ncbi_id_2)

        try:
            time.sleep(0.5)  # Rate limit
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "phylogenetic-cards/1.0")
            with urllib.request.urlopen(req, timeout=30, context=self._timetree_ssl) as resp:
                text = resp.read().decode().strip()
            if not text:
                print(f"    TimeTree returned empty response for {ncbi_id_1}/{ncbi_id_2}")
                return None
            lines = text.split("\n")
            if len(lines) < 2:
                return None
            headers = lines[0].split(",")
            values = lines[1].split(",")
            row = dict(zip(headers, values))
            age = row.get("precomputed_age")
            if age:
                return round(float(age), 2)
            return None
        except (urllib.error.URLError, ValueError) as exc:
            print(f"    Warning: TimeTree query failed for {ncbi_id_1}/{ncbi_id_2}: {exc}")
            return None
