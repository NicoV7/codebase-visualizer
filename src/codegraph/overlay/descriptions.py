"""Component descriptions: markdown files under <project>/.codegraph/descriptions/.

Plain files are the source of truth (reviewable in PRs, survive reindexes).
Each file: YAML frontmatter (symbol_id, hash_at_write, links) + an ADHD-style
body written by the calling agent per skills/code-graph/describe-style.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from codegraph.model.ids import slugify


@dataclass
class Description:
    symbol_id: str
    body: str
    hash_at_write: str | None = None
    links: list[str] | None = None
    stale: bool = False


def content_hash(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:16]


class DescriptionStore:
    def __init__(self, project_root: str | Path):
        self.dir = Path(project_root) / ".codegraph" / "descriptions"

    def _path(self, symbol_id: str) -> Path:
        return self.dir / f"{slugify(symbol_id)}.md"

    def write(self, desc: Description) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        front = {
            "symbol_id": desc.symbol_id,
            "hash_at_write": desc.hash_at_write,
            "links": desc.links or [],
        }
        path = self._path(desc.symbol_id)
        path.write_text(f"---\n{yaml.safe_dump(front, sort_keys=False)}---\n\n{desc.body.strip()}\n")
        return path

    def read(self, symbol_id: str) -> Description | None:
        path = self._path(symbol_id)
        if not path.exists():
            return None
        return self._parse(path)

    @staticmethod
    def _parse(path: Path) -> Description:
        text = path.read_text()
        if not text.startswith("---"):
            raise ValueError(f"description missing frontmatter: {path}")
        _, front_raw, body = text.split("---", 2)
        front = yaml.safe_load(front_raw)
        return Description(
            symbol_id=front["symbol_id"],
            body=body.strip(),
            hash_at_write=front.get("hash_at_write"),
            links=front.get("links") or [],
        )

    def all(self) -> list[Description]:
        if not self.dir.exists():
            return []
        return [self._parse(p) for p in sorted(self.dir.glob("*.md"))]

    def mark_stale(self, current_hashes: dict[str, str]) -> list[Description]:
        """Flag descriptions whose symbol content changed since they were written."""
        stale = []
        for desc in self.all():
            current = current_hashes.get(desc.symbol_id)
            if desc.hash_at_write and current and current != desc.hash_at_write:
                desc.stale = True
                stale.append(desc)
        return stale

    def undescribed(self, symbol_ids: list[str]) -> list[str]:
        return [sid for sid in symbol_ids if not self._path(sid).exists()]
