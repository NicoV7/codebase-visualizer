"""EngineAdapter protocol: the only seam between this package and any indexer.

Implementations must be swappable (CodeGraphContext today; a native
tree-sitter indexer or another MCP-backed engine later) without touching
overlay data, which is keyed by stable symbol IDs, never engine row IDs.
"""

from __future__ import annotations

from typing import Any, Protocol

from codegraph.model.graph import Graph


class EngineError(RuntimeError):
    """Raised loudly when the engine is missing, broken, or returns garbage.

    Never degrade silently: callers surface the message and the recovery path.
    """


class EngineAdapter(Protocol):
    def index(self, project_root: str, incremental: bool = False) -> dict[str, Any]:
        """Index (or refresh) a repository; returns engine stats."""
        ...

    def graph(self, project_root: str) -> Graph:
        """Full normalized graph for a project (functions, classes, files, imports)."""
        ...

    def trace(
        self, function_name: str, direction: str = "both", depth: int = 3
    ) -> list[dict[str, Any]]:
        """Caller/callee chains for a function. direction: in | out | both."""
        ...

    def query(self, cypher: str) -> list[dict[str, Any]]:
        """Raw graph query passthrough."""
        ...

    def doctor(self) -> list[str]:
        """Health check lines; raises EngineError on hard failure."""
        ...
