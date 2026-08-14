"""graph.json / overlay.json export contract shared by CLI, MCP, and the viz."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codegraph.model.graph import Graph
from codegraph.overlay.descriptions import DescriptionStore
from codegraph.overlay.reasons import ReasonLog


def export_graph(graph: Graph, project_root: str, out_path: str | Path) -> Path:
    store = DescriptionStore(project_root)
    log = ReasonLog(project_root)
    payload: dict[str, Any] = graph.to_dict()
    payload["descriptions"] = {d.symbol_id: {"body": d.body, "links": d.links} for d in store.all()}
    payload["reasons"] = [vars(r) for r in log.all()]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    return out
