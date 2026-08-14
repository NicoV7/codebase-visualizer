"""Isometric map DATA generator: components, zones, layout, edges, trace.

Aggregates the symbol graph into directory-level components and computes a
deterministic grid layout the single-file HTML template renders. Unlike the
LLM-scan approach that inspired the map, this is reproducible from the graph.
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


def build_isometric_data(
    graph: Graph,
    project_root: str,
    title: str,
    diff: DiffOverlay | None = None,
    scrub: bool = False,
) -> dict[str, Any]:
    comp_loc: dict[str, int] = defaultdict(int)
    comp_symbols: dict[str, list[str]] = defaultdict(list)
    node_comp: dict[str, str] = {}
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
        if node.line_start and node.line_end:
            comp_loc[comp] += max(1, node.line_end - node.line_start + 1)
        else:
            comp_loc[comp] += 5

    # Aggregate symbol edges to component edges with payload counts.
    comp_edges: dict[tuple[str, str, str], int] = defaultdict(int)
    for edge in graph.edges:
        src, dst = node_comp.get(edge.src), node_comp.get(edge.dst)
        if src and dst and src != dst:
            kind = "uses" if edge.kind in ("imports", "uses_library") else edge.kind
            comp_edges[(src, dst, kind)] += 1

    # Diff badges per component.
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

    max_loc = max(comp_loc.values(), default=1)
    ordered = sorted(comp_loc, key=lambda c: -comp_loc[c])
    structures = []
    grid_positions = _layout(ordered, {c: _zone(c) if not c.startswith("lib/") else "external" for c in ordered})
    for comp in ordered:
        zone = "external" if comp.startswith("lib/") else _zone(comp)
        loc = comp_loc[comp]
        # log curve keeps the largest block ~6 units and small ones >=1
        height = max(1, round(6 * math.log1p(loc) / math.log1p(max_loc)))
        label = "external dependency" if scrub and zone == "external" else comp
        what = next(
            (descriptions[sid].body.split("\n")[0] for sid in comp_symbols[comp] if sid in descriptions),
            "",
        )
        structures.append(
            {
                "id": comp,
                "code": _code(comp),
                "name": label,
                "zone": zone,
                "loc": loc,
                "symbols": sorted(comp_symbols[comp])[:200],
                "gx": grid_positions[comp][0],
                "gy": grid_positions[comp][1],
                "h": height,
                "what": what,
                "diff": comp_diff.get(comp),
            }
        )

    edges = [
        {"src": s, "dst": d, "kind": k, "count": n}
        for (s, d, k), n in sorted(comp_edges.items(), key=lambda kv: -kv[1])
    ]
    data = {
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
    if scrub:
        blob = json.dumps(data)
        if _SENSITIVE.search(blob):
            data = json.loads(_SENSITIVE.sub("[scrubbed]", blob))
    return data


def _code(component: str) -> str:
    base = component.split("/")[-1]
    return (base[:2] if len(base) >= 2 else base.ljust(2, "x")).upper()


def _layout(ordered: list[str], zones: dict[str, str]) -> dict[str, tuple[int, int]]:
    """Deterministic zone-banded grid: each zone owns a gy band, components fill gx slots."""
    bands = {"entry": 0, "interface": 2, "core": 4, "storage": 6, "quality": 8, "external": 10}
    counters: dict[str, int] = defaultdict(int)
    positions = {}
    for comp in ordered:
        band = bands.get(zones[comp], 4)
        slot = counters[zones[comp]]
        counters[zones[comp]] += 1
        positions[comp] = (slot * 3, band + (slot % 2))
    return positions


def _trace(structures: list[dict], edges: list[dict]) -> list[dict]:
    """Greedy walk from the entry zone along the heaviest edges, max 12 steps."""
    by_id = {s["id"]: s for s in structures}
    entry = next((s["id"] for s in structures if s["zone"] == "entry"), None)
    if entry is None and structures:
        entry = structures[0]["id"]
    steps, seen, current = [], set(), entry
    out_edges: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        out_edges[e["src"]].append(e)
    while current and current not in seen and len(steps) < 12:
        seen.add(current)
        steps.append({"structure": current, "note": f"{by_id[current]['zone']} · {by_id[current]['loc']} LOC"})
        candidates = [e["dst"] for e in out_edges[current] if e["dst"] not in seen]
        # libraries are trace dead-ends; stay inside the project when possible
        internal = [c for c in candidates if by_id[c]["zone"] != "external"]
        current = (internal or candidates or [None])[0]
    return steps
