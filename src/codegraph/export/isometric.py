"""2D isometric map DATA: thin wrapper over the shared city builder.

Kept as a module so the public API (`build_isometric_data`, `component_of`)
survives the city.py refactor unchanged.
"""

from __future__ import annotations

from typing import Any

from codegraph.diff.pr_overlay import DiffOverlay
from codegraph.export.city import ZONES, build_city_data, component_of  # noqa: F401
from codegraph.model.graph import Graph


def build_isometric_data(
    graph: Graph,
    project_root: str,
    title: str,
    diff: DiffOverlay | None = None,
    scrub: bool = False,
) -> dict[str, Any]:
    return build_city_data(
        graph, project_root, title, diff=diff, scrub=scrub, detail=False
    )
