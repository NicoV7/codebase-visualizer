"""Line-level PR overlay: git diff hunks intersected with symbol line spans.

Finer than symbol-level change detection: each node gets the exact added and
removed line numbers touching it, so the map can render +N/−M per component
and show the raw hunks on click.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from unidiff import PatchSet

from codegraph.model.graph import Graph


@dataclass
class NodeDiff:
    symbol_id: str
    added_lines: list[int] = field(default_factory=list)
    removed_lines: list[int] = field(default_factory=list)
    hunks: list[str] = field(default_factory=list)


@dataclass
class DiffOverlay:
    base: str
    head: str
    per_node: list[NodeDiff] = field(default_factory=list)
    unmapped_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "base": self.base,
            "head": self.head,
            "per_node": [vars(d) for d in self.per_node],
            "unmapped_files": self.unmapped_files,
        }


def git_diff(project_root: str, base: str, head: str = "HEAD") -> str:
    proc = subprocess.run(
        ["git", "-C", project_root, "diff", f"{base}...{head}"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()[-300:]}")
    return proc.stdout


def build_overlay(graph: Graph, diff_text: str, project_root: str, base: str, head: str) -> DiffOverlay:
    root = Path(project_root)
    # Group symbol spans by repo-relative path for hunk intersection.
    spans: dict[str, list] = {}
    for node in graph.nodes:
        if node.path and node.line_start and node.line_end:
            rel = Path(node.path)
            try:
                rel = rel.relative_to(root)
            except ValueError:
                pass
            spans.setdefault(rel.as_posix(), []).append(node)

    overlay = DiffOverlay(base=base, head=head)
    per_node: dict[str, NodeDiff] = {}
    for patched_file in PatchSet(diff_text):
        rel_path = patched_file.path
        file_nodes = spans.get(rel_path)
        if not file_nodes:
            overlay.unmapped_files.append(rel_path)
            continue
        for hunk in patched_file:
            hunk_str = str(hunk)
            touched: set[str] = set()
            for line in hunk:
                for node in file_nodes:
                    nd = None
                    if line.is_added and node.line_start <= line.target_line_no <= node.line_end:
                        nd = per_node.setdefault(node.id, NodeDiff(symbol_id=node.id))
                        nd.added_lines.append(line.target_line_no)
                    elif line.is_removed and node.line_start <= line.source_line_no <= node.line_end:
                        nd = per_node.setdefault(node.id, NodeDiff(symbol_id=node.id))
                        nd.removed_lines.append(line.source_line_no)
                    if nd is not None and node.id not in touched:
                        touched.add(node.id)
                        nd.hunks.append(hunk_str)
    overlay.per_node = list(per_node.values())
    return overlay
