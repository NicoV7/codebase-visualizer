"""Reasoning log: why a symbol exists or changed, one JSONL entry per reason.

Append-only <project>/.codegraph/reasons.jsonl — committable, reviewable,
and the single source of truth `why_trace` reads from.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Reason:
    symbol_id: str
    why: str
    kind: str = "exists"  # exists | changed
    source: str = "manual"  # adr | pr | manual | agent
    trace_id: str | None = None
    pr_number: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class ReasonLog:
    def __init__(self, project_root: str | Path):
        self.path = Path(project_root) / ".codegraph" / "reasons.jsonl"

    def record(self, reason: Reason) -> Reason:
        if reason.kind not in ("exists", "changed"):
            raise ValueError(f"kind must be exists|changed, got {reason.kind!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(reason)) + "\n")
        return reason

    def all(self) -> list[Reason]:
        if not self.path.exists():
            return []
        return [Reason(**json.loads(line)) for line in self.path.read_text().splitlines() if line]

    def for_symbol(self, symbol_id: str) -> list[Reason]:
        return [r for r in self.all() if r.symbol_id == symbol_id]

    def for_trace(self, trace_id: str) -> list[Reason]:
        return [r for r in self.all() if r.trace_id == trace_id]
