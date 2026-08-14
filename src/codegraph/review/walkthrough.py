"""Walkthrough builder: ordered comprehension stops for what an AI just built.

Pure function over the graph, diff overlay, and overlay stores. Ordering is
execution order (topological over call edges, entry zone first) so the tour
reads like the program runs. Every cap surfaces its total — a truncated tour
must say so, or the engineer believes they reviewed everything.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codegraph.diff.pr_overlay import DiffOverlay
from codegraph.export.city import _zone, component_of
from codegraph.model.graph import Graph

MAX_STOPS_CHANGED = 80
MAX_STOPS_CONTEXT = 40
MAX_SNIPPET_LINES = 80
MAX_HUNKS_PER_STOP = 5
MAX_NEIGHBORS = 15
MAX_TRACE_HOPS = 12

_ZONE_ORDER = ["entry", "interface", "core", "storage", "quality", "external"]


def build_walkthrough(
    graph: Graph,
    project_root: str,
    diff: DiffOverlay | None,
    descriptions: dict[str, Any],
    reasons: list[Any],
    understanding: dict[str, str],
    scope: str = "diff",
) -> dict[str, Any]:
    nodes = {n.id: n for n in graph.nodes if n.kind in ("function", "class")}
    diff_by_sid = {d.symbol_id: d for d in (diff.per_node if diff else [])}

    if scope == "diff":
        changed = [sid for sid in diff_by_sid if sid in nodes]
    else:
        changed = list(nodes)
    changed_set = set(changed)

    callers_of: dict[str, list[str]] = defaultdict(list)
    callees_of: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.kind == "calls" and edge.src in nodes and edge.dst in nodes:
            callees_of[edge.src].append(edge.dst)
            callers_of[edge.dst].append(edge.src)

    ordered_changed = _execution_order(changed_set, callers_of, callees_of, nodes, project_root)
    context = sorted(
        {
            caller
            for sid in changed_set
            for caller in callers_of[sid]
            if caller not in changed_set and caller in nodes
        },
        key=lambda sid: _sort_key(sid, nodes, project_root),
    )

    stops: list[dict[str, Any]] = []
    for sid in ordered_changed[:MAX_STOPS_CHANGED]:
        stops.append(_stop(sid, "changed", nodes, diff_by_sid, descriptions, reasons,
                           understanding, callers_of, callees_of, project_root))
    for sid in context[:MAX_STOPS_CONTEXT]:
        stop = _stop(sid, "context", nodes, diff_by_sid, descriptions, reasons,
                     understanding, callers_of, callees_of, project_root)
        stop["context_for"] = sorted(c for c in callees_of[sid] if c in changed_set)
        stops.append(stop)
    for i, stop in enumerate(stops):
        stop["seq"] = i + 1

    total = min(len(ordered_changed), MAX_STOPS_CHANGED) + min(len(context), MAX_STOPS_CONTEXT)
    return {
        "base": diff.base if diff else None,
        "head": diff.head if diff else None,
        "scope": scope,
        "stops": stops,
        "stops_total": len(ordered_changed) + len(context),
        "truncated": len(ordered_changed) > MAX_STOPS_CHANGED or len(context) > MAX_STOPS_CONTEXT,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shown": total,
    }


def _sort_key(sid: str, nodes: dict, project_root: str):
    node = nodes[sid]
    comp = (component_of(node.path, project_root) if node.path else None) or "~"
    zone = "external" if comp.startswith("lib/") else _zone(comp)
    return (_ZONE_ORDER.index(zone), comp, node.path or "~", node.line_start or 0, sid)


def _execution_order(changed: set, callers_of: dict, callees_of: dict, nodes: dict, project_root: str) -> list[str]:
    """Depth-first chains from entry-first roots, deterministic.

    Each root is followed down its whole call chain before the next root
    starts, so a capped tour keeps complete stories — breadth-first fronted
    every uncalled symbol and the cap sliced off all the depth."""
    def key(sid: str):
        return _sort_key(sid, nodes, project_root)

    roots = sorted(
        (s for s in changed if not any(c in changed and c != s for c in callers_of[s])),
        key=key,
    )
    ordered: list[str] = []
    visited: set[str] = set()

    def dfs(start: str) -> None:
        stack = [start]
        while stack:
            sid = stack.pop()
            if sid in visited:
                continue
            visited.add(sid)
            ordered.append(sid)
            children = sorted(
                {c for c in callees_of[sid] if c in changed and c not in visited},
                key=key, reverse=True,
            )
            stack.extend(children)  # reversed: smallest-key callee pops first

    for root in roots:
        dfs(root)
    while len(visited) < len(changed):  # cycle islands have no root
        dfs(min((s for s in changed if s not in visited), key=key))
    return ordered


def _snippet(node: Any) -> dict[str, Any]:
    if not node.path or not node.line_start:
        return {"lines": [], "shown": 0, "total": 0, "truncated": False}
    try:
        lines = Path(node.path).read_text(errors="replace").splitlines()
    except OSError:
        return {"lines": [], "shown": 0, "total": 0, "truncated": False}
    start, end = node.line_start - 1, node.line_end or node.line_start
    body = lines[start:end]
    return {
        "lines": body[:MAX_SNIPPET_LINES],
        "shown": min(len(body), MAX_SNIPPET_LINES),
        "total": len(body),
        "truncated": len(body) > MAX_SNIPPET_LINES,
    }


def _trace_path(sid: str, callers_of: dict, nodes: dict, project_root: str) -> list[dict[str, Any]]:
    """Shortest caller chain from an entry point down to `sid`, entry first.

    BFS backwards over callers; a hop in the entry zone (or with no callers)
    is a root. Deterministic: callers explored in _sort_key order."""
    def _is_root(s: str) -> bool:
        node = nodes[s]
        comp = (component_of(node.path, project_root) if node.path else None) or "~"
        return _zone(comp) == "entry" or not callers_of[s]

    parent: dict[str, str | None] = {sid: None}
    queue, root = [sid], None
    while queue and root is None:
        current = queue.pop(0)
        if _is_root(current):
            root = current
            break
        for caller in sorted(set(callers_of[current]), key=lambda s: _sort_key(s, nodes, project_root)):
            if caller in nodes and caller not in parent:
                parent[caller] = current
                queue.append(caller)
    if root is None:  # unreachable roots (cycle island): the symbol is its own path
        root = sid
    chain = []
    cursor: str | None = root
    while cursor is not None:
        chain.append(cursor)
        cursor = parent.get(cursor)
    hops = []
    for s in chain:
        node = nodes[s]
        try:
            rel = Path(node.path).relative_to(project_root).as_posix() if node.path else "?"
        except ValueError:
            rel = node.path or "?"
        hops.append({
            "symbol_id": s,
            "name": node.name,
            "component": (component_of(node.path, project_root) if node.path else None) or "?",
            "file": rel,
            "line": node.line_start,
        })
    return hops


def _stop(sid, kind, nodes, diff_by_sid, descriptions, reasons, understanding,
          callers_of, callees_of, project_root) -> dict[str, Any]:
    node = nodes[sid]
    comp = (component_of(node.path, project_root) if node.path else None) or "?"
    desc = descriptions.get(sid)
    nd = diff_by_sid.get(sid)
    hunks = list(dict.fromkeys(nd.hunks))[:MAX_HUNKS_PER_STOP] if nd else []
    neighbors = lambda ids: [
        {"id": i, "name": i.split("::")[-1]} for i in sorted(set(ids))[:MAX_NEIGHBORS]
    ]
    return {
        "kind": kind,
        "symbol_id": sid,
        "name": node.name,
        "component": comp,
        "zone": "external" if comp.startswith("lib/") else _zone(comp),
        "file": node.path,
        "line_start": node.line_start,
        "line_end": node.line_end,
        "snippet": _snippet(node),
        "diff": {
            "added": len(nd.added_lines),
            "removed": len(nd.removed_lines),
            "hunks": hunks,
            "hunks_total": len(set(nd.hunks)),
        } if nd else None,
        "what": getattr(desc, "body", None),
        "what_stale": bool(getattr(desc, "stale", False)),
        "gap": desc is None,
        "reasons": [
            {"why": r.why, "kind": r.kind, "source": r.source, "created_at": r.created_at}
            for r in reasons if r.symbol_id == sid
        ],
        "trace_path": (tp := _trace_path(sid, callers_of, nodes, project_root))[:MAX_TRACE_HOPS],
        "trace_path_total": len(tp),
        "callers": neighbors(callers_of[sid]),
        "callers_total": len(set(callers_of[sid])),
        "callees": neighbors(callees_of[sid]),
        "callees_total": len(set(callees_of[sid])),
        "understanding": understanding.get(sid, "unreviewed"),
    }
