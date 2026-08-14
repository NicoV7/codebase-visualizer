"""CodeGraphService: the single facade every surface (CLI, MCP, UI) calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codegraph.diff.pr_overlay import DiffOverlay, build_overlay, git_diff
from codegraph.engine.cgc_adapter import CgcAdapter
from codegraph.engine.protocol import EngineAdapter
from codegraph.export.graphjson import export_graph
from codegraph.export.isometric import build_isometric_data
from codegraph.model.graph import Graph, synthesize_library_nodes
from codegraph.overlay.descriptions import Description, DescriptionStore, content_hash
from codegraph.overlay.reasons import Reason, ReasonLog


class CodeGraphService:
    def __init__(self, project_root: str, engine: EngineAdapter | None = None):
        self.project_root = str(Path(project_root).resolve())
        self.engine = engine or CgcAdapter()
        self.descriptions = DescriptionStore(self.project_root)
        self.reasons = ReasonLog(self.project_root)

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

    def export_graphjson(self, out_path: str) -> str:
        return str(export_graph(self.graph(), self.project_root, out_path))

    def export_isometric(
        self, out_path: str, title: str | None = None, base: str | None = None, scrub: bool = False
    ) -> str:
        diff = self.diff(base) if base else None
        data = build_isometric_data(
            self.graph(),
            self.project_root,
            title or Path(self.project_root).name,
            diff=diff,
            scrub=scrub,
        )
        template = Path(__file__).parent.parent.parent / "viz" / "isometric-template.html"
        if not template.exists():
            # installed-package fallback: template ships inside the package
            template = Path(__file__).parent / "viz" / "isometric-template.html"
        if not template.exists():
            raise FileNotFoundError(f"isometric template not found at {template}")
        html = template.read_text().replace(
            "/*__CODEGRAPH_DATA__*/", "window.CODEGRAPH_DATA = " + json.dumps(data) + ";"
        )
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        return str(out)

    def doctor(self) -> list[str]:
        lines = self.engine.doctor()
        cg_dir = Path(self.project_root) / ".codegraph"
        lines.append(f"overlay dir: {cg_dir} ({'present' if cg_dir.exists() else 'not yet created'})")
        lines.append(f"descriptions: {len(self.descriptions.all())}")
        lines.append(f"reasons: {len(self.reasons.all())}")
        return lines
