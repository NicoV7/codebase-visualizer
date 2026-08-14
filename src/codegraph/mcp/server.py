"""code-graph MCP server: search/trace/query/diff/describe/reason tools.

Tool names mirror codebase-memory-mcp where semantics match, so agents
carry their intuition over. Description generation stays in the calling
agent (guided by the skill pack) — this server stores, never generates.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from codegraph.service import CodeGraphService


def build_server(project_root: str) -> FastMCP:
    mcp = FastMCP("code-graph")
    svc = CodeGraphService(project_root)

    @mcp.tool()
    def index_repo(incremental: bool = False) -> dict[str, Any]:
        """Index or refresh the project into the code graph; reports stale descriptions."""
        return svc.index(incremental=incremental)

    @mcp.tool()
    def search_graph(name_pattern: str, kind: str | None = None, limit: int = 25) -> list[dict]:
        """Find symbols by (case-insensitive) name substring; optional kind filter."""
        pattern = name_pattern.lower()
        nodes = [
            vars(n)
            for n in svc.graph().nodes
            if pattern in n.name.lower() and (kind is None or n.kind == kind)
        ]
        return nodes[: max(1, min(limit, 200))]

    @mcp.tool()
    def trace_path(function_name: str, direction: str = "both", depth: int = 3) -> list[dict]:
        """Trace callers (in) / callees (out) of a function through the call graph."""
        return svc.trace(function_name, direction=direction, depth=depth)

    @mcp.tool()
    def query_graph(cypher: str) -> list[dict]:
        """Run a raw Cypher query against the code graph."""
        return svc.engine.query(cypher)

    @mcp.tool()
    def get_architecture() -> dict[str, Any]:
        """Component-level view: directory components, aggregated edges, zones, trace."""
        from codegraph.export.isometric import build_isometric_data

        data = build_isometric_data(svc.graph(), svc.project_root, title=svc.project_root)
        data.pop("descriptions", None)
        return data

    @mcp.tool()
    def diff_overlay(base: str, head: str = "HEAD") -> dict[str, Any]:
        """Line-level +/− per symbol between two git refs, for PR visualization."""
        return svc.diff(base, head).to_dict()

    @mcp.tool()
    def describe_component(symbol_id: str) -> dict[str, Any]:
        """Read a component's stored description (ADHD-style, with links)."""
        desc = svc.descriptions.read(symbol_id)
        if desc is None:
            return {"symbol_id": symbol_id, "description": None}
        return {"symbol_id": symbol_id, "description": desc.body, "links": desc.links}

    @mcp.tool()
    def set_description(symbol_id: str, markdown: str, links: list[str] | None = None) -> str:
        """Store a description written per the code-graph describe-style skill."""
        return svc.describe(symbol_id, markdown, links=links)

    @mcp.tool()
    def list_undescribed(limit: int = 50) -> list[str]:
        """Symbols without descriptions — drive the describe-the-codebase agent loop."""
        ids = [n.id for n in svc.graph().nodes if n.kind in ("function", "class")]
        return svc.descriptions.undescribed(ids)[: max(1, min(limit, 500))]

    @mcp.tool()
    def record_reason(
        symbol_id: str,
        why: str,
        kind: str = "exists",
        source: str = "agent",
        trace_id: str | None = None,
        pr_number: int | None = None,
    ) -> dict[str, Any]:
        """Log why a symbol exists or changed (kind: exists|changed)."""
        return vars(
            svc.record_reason(
                symbol_id=symbol_id, why=why, kind=kind, source=source,
                trace_id=trace_id, pr_number=pr_number,
            )
        )

    @mcp.tool()
    def why_trace(symbol_or_trace_id: str) -> list[dict]:
        """Read the reasoning log for a symbol or trace id."""
        return [vars(r) for r in svc.why(symbol_or_trace_id)]

    @mcp.tool()
    def get_comprehension() -> dict[str, Any]:
        """Repo understanding state: % understood, counts, unreviewed symbols.

        Use this to tell the engineer what they have not reviewed yet."""
        result = svc.comprehension()
        result["unreviewed"] = result["unreviewed"][:100]
        return result

    @mcp.tool()
    def build_walkthrough(base: str | None = None, all_scope: bool = False) -> dict[str, Any]:
        """Ordered comprehension stops for a diff (or whole repo) — run the
        tour conversationally: present each stop's WHAT/WHY/code, then
        mark_understood when the engineer confirms."""
        return svc.build_walkthrough(base=base, all_scope=all_scope)

    @mcp.tool()
    def mark_understood(symbol_id: str, state: str = "walked") -> dict[str, Any]:
        """Record that the engineer walked through (or owns) a symbol.

        Only call after they actually confirmed understanding — this ledger
        is their comprehension record, not a checkbox."""
        entry = svc.mark_understood(symbol_id, state)
        return {"recorded": vars(entry), "comprehension": svc.comprehension()}

    return mcp
