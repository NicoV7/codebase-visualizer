"""Shared city DATA builder for both the 2D isometric map and the 3D city.

Aggregates the symbol graph into directory-level components with a
deterministic zone-banded layout. `detail=True` additionally emits the
expansion hierarchy (component -> files -> symbols) and symbol-level call
edges so the 3D view can open components in place. Caps are never silent:
every capped list carries its total.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from codegraph.diff.pr_overlay import DiffOverlay
from codegraph.model.graph import Graph
from codegraph.overlay.descriptions import DescriptionStore
from codegraph.overlay.reasons import ReasonLog

_SENSITIVE = re.compile(
    r"(secret|token|password|credential|api[_-]?key|\.env|amazonaws|blob\.core)", re.I
)

MAX_STRUCTURE_SYMBOLS = 200
MAX_FILES_PER_COMPONENT = 60
MAX_SYMBOLS_PER_FILE = 120
MAX_SYMBOL_EDGES = 5000


def component_of(path: str, project_root: str, depth: int = 2) -> str | None:
    try:
        rel = Path(path).relative_to(project_root)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return "/".join(parts[: depth if len(parts) > depth else max(1, len(parts) - 1)]) or parts[0]


def _zone(component: str) -> str:
    name = component.lower()
    if any(k in name for k in ("cli", "main", "ui", "web", "frontend", "pages")):
        return "entry"
    if any(k in name for k in ("test", "spec", "fixture")):
        return "quality"
    if any(k in name for k in ("db", "store", "storage", "model", "migration", "sql")):
        return "storage"
    if any(k in name for k in ("api", "server", "routes", "mcp", "hooks")):
        return "interface"
    return "core"


ZONES = {
    "entry": {"label": "ENTRY / UI", "color": "#c9d96e"},
    "interface": {"label": "APIS + INTERFACES", "color": "#8fa3d9"},
    "core": {"label": "CORE DOMAIN", "color": "#b0b89a"},
    "storage": {"label": "STORAGE", "color": "#d9c98f"},
    "quality": {"label": "TESTS + QUALITY", "color": "#a9a9a9"},
    "external": {"label": "EXTERNAL LIBRARIES", "color": "#d98f6e"},
}


def _node_loc(node: Any) -> int:
    if node.line_start and node.line_end:
        return max(1, node.line_end - node.line_start + 1)
    return 5


def build_city_data(
    graph: Graph,
    project_root: str,
    title: str,
    diff: DiffOverlay | None = None,
    scrub: bool = False,
    detail: bool = False,
) -> dict[str, Any]:
    comp_loc: dict[str, int] = defaultdict(int)
    comp_symbols: dict[str, list[str]] = defaultdict(list)
    node_comp: dict[str, str] = {}
    nodes_by_id = graph.node_index()
    for node in graph.nodes:
        if node.kind == "library":
            comp = f"lib/{node.name}"
        elif node.path:
            comp = component_of(node.path, project_root)
            if comp is None:
                continue
        else:
            continue
        node_comp[node.id] = comp
        comp_symbols[comp].append(node.id)
        comp_loc[comp] += _node_loc(node)

    comp_edges: dict[tuple[str, str, str], int] = defaultdict(int)
    sym_edges: dict[tuple[str, str], int] = defaultdict(int)
    for edge in graph.edges:
        src, dst = node_comp.get(edge.src), node_comp.get(edge.dst)
        if not src or not dst:
            continue
        if src != dst:
            kind = "uses" if edge.kind in ("imports", "uses_library") else edge.kind
            comp_edges[(src, dst, kind)] += 1
        if detail and edge.kind == "calls":
            sym_edges[(edge.src, edge.dst)] += 1

    comp_diff: dict[str, dict[str, int]] = defaultdict(lambda: {"added": 0, "removed": 0})
    if diff:
        for nd in diff.per_node:
            comp = node_comp.get(nd.symbol_id)
            if comp:
                comp_diff[comp]["added"] += len(nd.added_lines)
                comp_diff[comp]["removed"] += len(nd.removed_lines)

    desc_store = DescriptionStore(project_root)
    descriptions = {d.symbol_id: d for d in desc_store.all()}
    reasons = ReasonLog(project_root).all()

    symbol_index: list[str] = sorted(node_comp) if detail else []
    sym_i = {sid: i for i, sid in enumerate(symbol_index)}

    max_loc = max(comp_loc.values(), default=1)
    ordered = sorted(comp_loc, key=lambda c: -comp_loc[c])
    grid_positions = _layout(
        ordered, {c: "external" if c.startswith("lib/") else _zone(c) for c in ordered}
    )
    structures = []
    for comp in ordered:
        zone = "external" if comp.startswith("lib/") else _zone(comp)
        loc = comp_loc[comp]
        height = max(1, round(6 * math.log1p(loc) / math.log1p(max_loc)))
        label = "external dependency" if scrub and zone == "external" else comp
        what = next(
            (descriptions[sid].body.split("\n")[0] for sid in comp_symbols[comp] if sid in descriptions),
            "",
        )
        all_symbols = sorted(comp_symbols[comp])
        structure = {
            "id": comp,
            "code": _code(comp),
            "name": label,
            "zone": zone,
            "loc": loc,
            "symbols": all_symbols[:MAX_STRUCTURE_SYMBOLS],
            "symbols_total": len(all_symbols),
            "gx": grid_positions[comp][0],
            "gy": grid_positions[comp][1],
            "h": height,
            "what": what,
            "diff": comp_diff.get(comp),
        }
        if detail:
            structure["children"] = _children(
                comp_symbols[comp], nodes_by_id, sym_i, project_root
            )
        structures.append(structure)

    edges = [
        {"src": s, "dst": d, "kind": k, "count": n}
        for (s, d, k), n in sorted(comp_edges.items(), key=lambda kv: -kv[1])
    ]
    data: dict[str, Any] = {
        "title": title,
        "zones": ZONES,
        "structures": structures,
        "edges": edges,
        "trace": _trace(structures, edges),
        "stats": {
            "components": len(structures),
            "symbols": len(node_comp),
            "loc_indexed": sum(comp_loc.values()),
            "diff": {"base": diff.base, "head": diff.head} if diff else None,
        },
        "descriptions": {
            sid: {"body": d.body, "links": d.links, "stale": d.stale}
            for sid, d in descriptions.items()
        },
        "reasons": [vars(r) for r in reasons],
    }
    if detail:
        data["symbol_index"] = symbol_index
        ranked = sorted(sym_edges.items(), key=lambda kv: -kv[1])
        data["symbol_edges"] = [
            [sym_i[s], sym_i[d], n] for (s, d), n in ranked[:MAX_SYMBOL_EDGES]
        ]
        data["symbol_edges_total"] = len(sym_edges)
    if scrub:
        blob = json.dumps(data)
        if _SENSITIVE.search(blob):
            data = json.loads(_SENSITIVE.sub("[scrubbed]", blob))
    return data


def _children(
    symbol_ids: list[str],
    nodes_by_id: dict[str, Any],
    sym_i: dict[str, int],
    project_root: str,
) -> dict[str, Any]:
    by_file: dict[str, list[Any]] = defaultdict(list)
    for sid in symbol_ids:
        node = nodes_by_id.get(sid)
        if node is None or node.kind not in ("function", "class") or not node.path:
            continue
        try:
            rel = Path(node.path).relative_to(project_root).as_posix()
        except ValueError:
            rel = node.path
        by_file[rel].append(node)

    files = []
    for rel, nodes in by_file.items():
        nodes.sort(key=lambda n: n.line_start or 0)
        files.append(
            {
                "path": rel,
                "loc": sum(_node_loc(n) for n in nodes),
                "symbols": [
                    {
                        "i": sym_i[n.id],
                        "name": n.name,
                        "kind": n.kind,
                        "loc": _node_loc(n),
                        "complexity": n.complexity,
                        "line_start": n.line_start,
                    }
                    for n in sorted(nodes, key=lambda n: -_node_loc(n))[:MAX_SYMBOLS_PER_FILE]
                ],
                "symbols_total": len(nodes),
            }
        )
    files.sort(key=lambda f: -f["loc"])
    truncated = len(files) > MAX_FILES_PER_COMPONENT or any(
        f["symbols_total"] > len(f["symbols"]) for f in files
    )
    return {
        "files": files[:MAX_FILES_PER_COMPONENT],
        "files_total": len(files),
        "symbols_total": sum(f["symbols_total"] for f in files),
        "truncated": truncated,
    }


def _code(component: str) -> str:
    base = component.split("/")[-1]
    return (base[:2] if len(base) >= 2 else base.ljust(2, "x")).upper()


def _layout(
    ordered: list[str], zones: dict[str, str], row_width: int = 8
) -> dict[str, tuple[int, int]]:
    """Deterministic zone-banded grid, wrapping into rows so large zones
    stay compact instead of marching diagonally off-canvas."""
    zone_order = ["entry", "interface", "core", "storage", "quality", "external"]
    counts: dict[str, int] = defaultdict(int)
    for comp in ordered:
        counts[zones[comp]] += 1
    band_start: dict[str, int] = {}
    cursor = 0
    for z in zone_order:
        band_start[z] = cursor
        rows = max(1, -(-counts[z] // row_width))
        cursor += rows * 3 + 1
    counters: dict[str, int] = defaultdict(int)
    positions = {}
    for comp in ordered:
        zone = zones[comp]
        slot = counters[zone]
        counters[zone] += 1
        col, row = slot % row_width, slot // row_width
        positions[comp] = (col * 3, band_start.get(zone, 0) + row * 3)
    return positions


def _trace(structures: list[dict], edges: list[dict]) -> list[dict]:
    """Greedy walk from the entry zone along the heaviest edges, max 12 steps."""
    by_id = {s["id"]: s for s in structures}
    entry = next((s["id"] for s in structures if s["zone"] == "entry"), None)
    if entry is None and structures:
        entry = structures[0]["id"]
    steps: list[dict] = []
    seen: set[str] = set()
    current = entry
    out_edges: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        out_edges[e["src"]].append(e)
    while current and current not in seen and len(steps) < 12:
        seen.add(current)
        steps.append(
            {"structure": current, "note": f"{by_id[current]['zone']} · {by_id[current]['loc']} LOC"}
        )
        candidates = [e["dst"] for e in out_edges[current] if e["dst"] not in seen]
        # libraries are trace dead-ends; stay inside the project when possible
        internal = [c for c in candidates if by_id[c]["zone"] != "external"]
        current = (internal or candidates or [None])[0]
    return steps
