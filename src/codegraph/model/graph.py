"""Canonical graph shapes shared by CLI, MCP tools, and exports.

The engine's raw nodes/edges are normalized here; library nodes are
synthesized so external imports render as separate components.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Node:
    id: str
    kind: str  # function | class | file | module | package | library
    name: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    lang: str | None = None
    complexity: int | None = None
    is_external: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # calls | imports | contains | inherits | uses_library
    line: int | None = None


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def node_index(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [asdict(n) for n in self.nodes], "edges": [asdict(e) for e in self.edges]}


def synthesize_library_nodes(graph: Graph, project_root: str) -> Graph:
    """Collapse import targets outside the project into one node per package.

    An import edge whose destination node lives outside ``project_root`` (or is
    flagged external by the engine) is redirected to a ``library`` node keyed by
    its top-level package name, so third-party modules appear as components.
    """
    from codegraph.model.ids import library_id

    index = graph.node_index()
    lib_nodes: dict[str, Node] = {}
    new_edges: list[Edge] = []
    for edge in graph.edges:
        dst = index.get(edge.dst)
        external = dst is not None and (
            dst.is_external or (dst.path and not dst.path.startswith(project_root))
        )
        if edge.kind == "imports" and external:
            package = (dst.name or "unknown").split(".")[0]
            lid = library_id(package)
            lib_nodes.setdefault(
                lid, Node(id=lid, kind="library", name=package, is_external=True)
            )
            new_edges.append(Edge(src=edge.src, dst=lid, kind="uses_library", line=edge.line))
        else:
            new_edges.append(edge)
    kept = [n for n in graph.nodes if not (n.is_external and n.kind != "library")]
    return Graph(nodes=kept + list(lib_nodes.values()), edges=new_edges)
