"""Understanding ledger: which symbols a human has actually reviewed/owned.

Append-only <project>/.codegraph/understanding.jsonl. `unreviewed` is never
written — it is the absence of a valid entry, including entries voided
because the symbol's content hash changed since review (understanding of
code that has since changed is no longer understanding).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATES = ("walked", "owned")


@dataclass
class UnderstandingEntry:
    symbol_id: str
    state: str  # walked | owned
    hash_at_review: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class UnderstandingLedger:
    def __init__(self, project_root: str | Path):
        self.path = Path(project_root) / ".codegraph" / "understanding.jsonl"

    def record(self, entry: UnderstandingEntry) -> UnderstandingEntry:
        if entry.state not in STATES:
            raise ValueError(f"state must be one of {STATES}, got {entry.state!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def all(self) -> list[UnderstandingEntry]:
        if not self.path.exists():
            return []
        return [
            UnderstandingEntry(**json.loads(line))
            for line in self.path.read_text().splitlines()
            if line
        ]

    def effective(self, current_hashes: dict[str, str]) -> dict[str, str]:
        """Latest valid state per symbol; hash drift voids back to unreviewed."""
        states: dict[str, str] = {}
        for entry in self.all():  # file order = time order (append-only)
            current = current_hashes.get(entry.symbol_id)
            if entry.hash_at_review and current and current == entry.hash_at_review:
                states[entry.symbol_id] = entry.state
            else:
                states.pop(entry.symbol_id, None)
        return states
