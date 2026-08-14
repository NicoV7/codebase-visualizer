"""CodeGraphContext adapter: drives the `cgc` CLI and parses its JSON output.

The CLI (not the private Python API) is the contract — CGC's internals move
between releases but `cgc query` JSON and `cgc index` are user-facing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from codegraph.engine.protocol import EngineError
from codegraph.model.graph import Edge, Graph, Node
from codegraph.model.ids import symbol_id

_QUERY_TIMEOUT_S = 120
_INDEX_TIMEOUT_S = 1800

_GRAPH_NODES_CYPHER = """
MATCH (f:Function)
WHERE f.name <> '<module>'
RETURN f.name AS name, f.path AS path, f.line_number AS line_start,
       f.end_line AS line_end, f.lang AS lang,
       f.cyclomatic_complexity AS complexity, f.is_dependency AS is_dependency,
       'function' AS kind
"""

_GRAPH_CLASSES_CYPHER = """
MATCH (c:Class)
RETURN c.name AS name, c.path AS path, c.line_number AS line_start,
       c.end_line AS line_end, c.lang AS lang,
       null AS complexity, c.is_dependency AS is_dependency, 'class' AS kind
"""

_CALL_EDGES_CYPHER = """
MATCH (a:Function)-[r:CALLS]->(b:Function)
WHERE a.name <> '<module>' AND b.name <> '<module>'
RETURN a.name AS src_name, a.path AS src_path,
       b.name AS dst_name, b.path AS dst_path
"""

_IMPORT_EDGES_CYPHER = """
MATCH (f:File)-[:IMPORTS]->(m:Module)
RETURN f.path AS src_path, m.name AS name, m.full_import_name AS full_import_name
"""


class CgcAdapter:
    def __init__(self, cgc_bin: str = "cgc"):
        self.cgc_bin = cgc_bin

    def _run(self, *args: str, timeout: int = _QUERY_TIMEOUT_S) -> str:
        # console-script installs put cgc next to the running interpreter,
        # which is not necessarily on the caller's PATH
        sibling = Path(sys.executable).parent / self.cgc_bin
        binary = shutil.which(self.cgc_bin) or (str(sibling) if sibling.exists() else None)
        if binary is None:
            raise EngineError(
                f"`{self.cgc_bin}` not found on PATH; install with "
                "`pip install codegraphcontext` or pass --cgc-bin"
            )
        proc = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode != 0:
            raise EngineError(
                f"cgc {' '.join(args[:2])} failed (exit {proc.returncode}): "
                f"{proc.stderr.strip()[-500:] or proc.stdout.strip()[-500:]}"
            )
        return proc.stdout

    @staticmethod
    def _parse_json(stdout: str) -> list[dict[str, Any]]:
        # cgc prints human preamble lines ("Using database: ...") before the JSON body.
        start = min(
            (i for i in (stdout.find("["), stdout.find("{")) if i != -1),
            default=-1,
        )
        if start == -1:
            raise EngineError(f"cgc returned no JSON: {stdout.strip()[:300]!r}")
        try:
            data = json.loads(stdout[start:])
        except json.JSONDecodeError as exc:
            raise EngineError(f"cgc returned unparseable JSON: {exc}") from exc
        return data if isinstance(data, list) else [data]

    def index(self, project_root: str, incremental: bool = False) -> dict[str, Any]:
        cmd = "update" if incremental else "index"
        out = self._run(cmd, project_root, timeout=_INDEX_TIMEOUT_S)
        return {"command": cmd, "output_tail": out.strip().splitlines()[-10:]}

    def query(self, cypher: str) -> list[dict[str, Any]]:
        return self._parse_json(self._run("query", cypher))

    def graph(self, project_root: str) -> Graph:
        nodes: list[Node] = []
        seen: set[str] = set()
        for row in self.query(_GRAPH_NODES_CYPHER) + self.query(_GRAPH_CLASSES_CYPHER):
            path = row.get("path")
            if path is not None and not str(path).startswith(project_root):
                continue
            sid = symbol_id(path or "?", row["name"], repo_root=project_root)
            if sid in seen:
                continue
            seen.add(sid)
            nodes.append(
                Node(
                    id=sid,
                    kind=row["kind"],
                    name=row["name"],
                    path=path,
                    line_start=row.get("line_start"),
                    line_end=row.get("line_end"),
                    lang=row.get("lang"),
                    complexity=row.get("complexity"),
                    is_external=bool(row.get("is_dependency")),
                )
            )
        edges: list[Edge] = []
        for row in self.query(_CALL_EDGES_CYPHER):
            if not row.get("src_path") or not row.get("dst_path"):
                continue
            edges.append(
                Edge(
                    src=symbol_id(row["src_path"], row["src_name"], repo_root=project_root),
                    dst=symbol_id(row["dst_path"], row["dst_name"], repo_root=project_root),
                    kind="calls",
                )
            )
        # top-level dirs and module basenames of the project distinguish
        # project-internal imports from third-party/stdlib packages
        project_tops: set[str] = set()
        for node in nodes:
            if node.path:
                try:
                    rel = Path(node.path).relative_to(project_root)
                except ValueError:
                    continue
                project_tops.add(rel.parts[0].removesuffix(".py"))
        module_nodes: dict[str, Node] = {}
        for row in self.query(_IMPORT_EDGES_CYPHER):
            if not row.get("src_path") or not str(row["src_path"]).startswith(project_root):
                continue
            full = row.get("full_import_name") or row.get("name") or "unknown"
            top = full.split(".")[0]
            external = top not in project_tops
            mid = f"module::{top}" if external else f"module::{full}"
            module_nodes.setdefault(
                mid, Node(id=mid, kind="module", name=top if external else full, is_external=external)
            )
            fid = symbol_id(row["src_path"], "<file>", repo_root=project_root)
            module_nodes.setdefault(
                fid,
                Node(id=fid, kind="file", name=Path(row["src_path"]).name, path=row["src_path"]),
            )
            edges.append(Edge(src=fid, dst=mid, kind="imports"))
        return Graph(nodes=nodes + list(module_nodes.values()), edges=edges)

    def trace(
        self, function_name: str, direction: str = "both", depth: int = 3
    ) -> list[dict[str, Any]]:
        if depth < 1 or depth > 10:
            raise EngineError(f"depth must be 1..10, got {depth}")
        # cgc query offers no parameter binding, so restrict to identifier chars
        # rather than escaping into the Cypher string.
        if not function_name.replace("_", "").replace(".", "").isalnum():
            raise EngineError(f"invalid function name: {function_name!r}")
        results: list[dict[str, Any]] = []
        if direction in ("in", "both"):
            rows = self.query(
                f"MATCH path = (caller:Function)-[:CALLS*1..{depth}]->(f:Function {{name: '{function_name}'}}) "
                "RETURN caller.name AS name, caller.path AS path, "
                "caller.line_number AS line, length(path) AS hops"
            )
            results += [{**r, "direction": "in"} for r in rows]
        if direction in ("out", "both"):
            rows = self.query(
                f"MATCH path = (f:Function {{name: '{function_name}'}})-[:CALLS*1..{depth}]->(callee:Function) "
                "RETURN callee.name AS name, callee.path AS path, "
                "callee.line_number AS line, length(path) AS hops"
            )
            results += [{**r, "direction": "out"} for r in rows]
        return results

    def doctor(self) -> list[str]:
        out = self._run("doctor")
        lines = [line for line in out.splitlines() if line.strip()]
        if any("✗" in line or "FAIL" in line for line in lines):
            raise EngineError("cgc doctor reported failures:\n" + "\n".join(lines[-15:]))
        return lines
