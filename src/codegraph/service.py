"""CodeGraphService: the single facade every surface (CLI, MCP, UI) calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codegraph.diff.pr_overlay import DiffOverlay, build_overlay, git_diff
from codegraph.engine.cgc_adapter import CgcAdapter
from codegraph.engine.protocol import EngineAdapter
from codegraph.export.graphjson import export_graph
from codegraph.model.graph import Graph, synthesize_library_nodes
from codegraph.overlay.descriptions import Description, DescriptionStore, content_hash
from codegraph.overlay.reasons import Reason, ReasonLog
from codegraph.overlay.understanding import UnderstandingEntry, UnderstandingLedger


class CodeGraphService:
    def __init__(self, project_root: str, engine: EngineAdapter | None = None):
        self.project_root = str(Path(project_root).resolve())
        self.engine = engine or CgcAdapter()
        self.descriptions = DescriptionStore(self.project_root)
        self.reasons = ReasonLog(self.project_root)
        self.understanding = UnderstandingLedger(self.project_root)

    def index(self, incremental: bool = False) -> dict[str, Any]:
        stats = self.engine.index(self.project_root, incremental=incremental)
        stale = self.descriptions.mark_stale(self._symbol_hashes())
        stats["stale_descriptions"] = [d.symbol_id for d in stale]
        return stats

    def graph(self) -> Graph:
        return synthesize_library_nodes(self.engine.graph(self.project_root), self.project_root)

    def _symbol_hashes(self) -> dict[str, str]:
        # hash the file slice locally: cgc's JSON-encoded `source` field is
        # unreliable (unescaped control chars / backslashes)
        from codegraph.model.ids import symbol_id

        rows = self.engine.query(
            "MATCH (f:Function) WHERE f.name <> '<module>' "
            "RETURN f.name AS name, f.path AS path, "
            "f.line_number AS line_start, f.end_line AS line_end"
        ) + self.engine.query(
            # classes too: ledger/description staleness must cover them
            "MATCH (c:Class) RETURN c.name AS name, c.path AS path, "
            "c.line_number AS line_start, c.end_line AS line_end"
        )
        file_lines: dict[str, list[str]] = {}
        hashes: dict[str, str] = {}
        for r in rows:
            path = r.get("path")
            if not path or not str(path).startswith(self.project_root):
                continue
            if path not in file_lines:
                try:
                    file_lines[path] = Path(path).read_text(errors="replace").splitlines()
                except OSError:
                    file_lines[path] = []
            lines = file_lines[path]
            start, end = r.get("line_start") or 1, r.get("line_end") or 0
            snippet = "\n".join(lines[start - 1 : end])
            hashes[symbol_id(path, r["name"], repo_root=self.project_root)] = content_hash(snippet)
        return hashes

    def trace(self, function_name: str, direction: str = "both", depth: int = 3) -> list[dict]:
        return self.engine.trace(function_name, direction=direction, depth=depth)

    def diff(self, base: str, head: str = "HEAD") -> DiffOverlay:
        text = git_diff(self.project_root, base, head)
        return build_overlay(self.graph(), text, self.project_root, base, head)

    def describe(self, sid: str, body: str, links: list[str] | None = None) -> str:
        source_hash = self._symbol_hashes().get(sid)
        path = self.descriptions.write(
            Description(symbol_id=sid, body=body, hash_at_write=source_hash, links=links)
        )
        return str(path)

    def why(self, sid_or_trace: str) -> list[Reason]:
        by_symbol = self.reasons.for_symbol(sid_or_trace)
        return by_symbol or self.reasons.for_trace(sid_or_trace)

    def record_reason(self, **kwargs: Any) -> Reason:
        return self.reasons.record(Reason(**kwargs))

    def build_walkthrough(self, base: str | None = None, all_scope: bool = False) -> dict[str, Any]:
        from codegraph.review.walkthrough import build_walkthrough

        hashes = self._symbol_hashes()
        self.descriptions.mark_stale(hashes)  # sets .stale on returned objects below
        descs = {d.symbol_id: d for d in self.descriptions.all()}
        for d in descs.values():
            current = hashes.get(d.symbol_id)
            d.stale = bool(d.hash_at_write and current and current != d.hash_at_write)
        return build_walkthrough(
            self.graph(),
            self.project_root,
            self.diff(base) if base and not all_scope else None,
            descs,
            self.reasons.all(),
            self.understanding.effective(hashes),
            scope="all" if all_scope or not base else "diff",
        )

    def mark_understood(self, symbol_id: str, state: str = "walked") -> UnderstandingEntry:
        hashes = self._symbol_hashes()
        return self.understanding.record(
            UnderstandingEntry(
                symbol_id=symbol_id, state=state, hash_at_review=hashes.get(symbol_id)
            )
        )

    def comprehension(self) -> dict[str, Any]:
        """Per-symbol understanding states + LOC-weighted percent understood."""
        states = self.understanding.effective(self._symbol_hashes())
        nodes = [n for n in self.graph().nodes if n.kind in ("function", "class")]
        loc = {n.id: max(1, (n.line_end or 1) - (n.line_start or 1) + 1) for n in nodes}
        total = sum(loc.values()) or 1
        understood = sum(loc.get(sid, 0) for sid, st in states.items() if st in ("walked", "owned"))
        unreviewed = sorted(n.id for n in nodes if n.id not in states)
        return {
            "states": states,
            "percent": round(100 * understood / total, 1),
            "counts": {
                "unreviewed": len(unreviewed),
                "walked": sum(1 for s in states.values() if s == "walked"),
                "owned": sum(1 for s in states.values() if s == "owned"),
            },
            "unreviewed": unreviewed,
        }

    def export_graphjson(self, out_path: str) -> str:
        return str(export_graph(self.graph(), self.project_root, out_path))

    def _viz_path(self, name: str) -> Path:
        candidate = Path(__file__).parent.parent.parent / "viz" / name
        if not candidate.exists():
            # installed-package fallback: viz/ ships inside the wheel
            candidate = Path(__file__).parent / "viz" / name
        if not candidate.exists():
            raise FileNotFoundError(
                f"viz asset {name!r} not found at {candidate}"
                + (" — run `node scripts/build-vendor.mjs`" if name.endswith(".js") else "")
            )
        return candidate

    def _render_template(self, template_name: str, replacements: dict[str, str], out_path: str) -> str:
        html = self._viz_path(template_name).read_text()
        for placeholder, value in replacements.items():
            marker = f"/*__{placeholder}__*/"
            if marker not in html:
                raise ValueError(f"template {template_name} is missing {marker}")
            html = html.replace(marker, value)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        return str(out)

    def _city_data(
        self,
        title: str | None,
        base: str | None,
        scrub: bool,
        detail: bool,
        review: dict[str, Any] | None = None,
    ) -> str:
        from codegraph.export.city import build_city_data

        data = build_city_data(
            self.graph(),
            self.project_root,
            title or Path(self.project_root).name,
            diff=self.diff(base) if base else None,
            scrub=scrub,
            detail=detail,
        )
        if detail:
            data["review"] = {
                "understanding": self.comprehension(),
                "served": False,
                **(review or {}),
            }
        # escape "</" so no description/source string can terminate the script tag
        payload = json.dumps(data).replace("</", "<\\/")
        return f"window.CODEGRAPH_DATA = {payload};"

    def export_isometric(
        self, out_path: str, title: str | None = None, base: str | None = None, scrub: bool = False
    ) -> str:
        return self._render_template(
            "isometric-template.html",
            {"CODEGRAPH_DATA": self._city_data(title, base, scrub, detail=False)},
            out_path,
        )

    def render_city3d(
        self,
        title: str | None = None,
        base: str | None = None,
        scrub: bool = False,
        review: dict[str, Any] | None = None,
    ) -> str:
        """City HTML as a string — shared by static export and the review server."""
        bundle = self._viz_path("vendor/three-bundle.min.js").read_text()
        html = self._viz_path("city3d-template.html").read_text()
        for placeholder, value in {
            "THREE_BUNDLE": bundle,
            "CODEGRAPH_DATA": self._city_data(title, base, scrub, detail=True, review=review),
        }.items():
            marker = f"/*__{placeholder}__*/"
            if marker not in html:
                raise ValueError(f"city3d template is missing {marker}")
            html = html.replace(marker, value)
        return html

    def export_city3d(
        self, out_path: str, title: str | None = None, base: str | None = None, scrub: bool = False
    ) -> str:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render_city3d(title, base, scrub))
        return str(out)

    def doctor(self) -> list[str]:
        lines = self.engine.doctor()
        cg_dir = Path(self.project_root) / ".codegraph"
        lines.append(f"overlay dir: {cg_dir} ({'present' if cg_dir.exists() else 'not yet created'})")
        lines.append(f"descriptions: {len(self.descriptions.all())}")
        lines.append(f"reasons: {len(self.reasons.all())}")
        return lines
