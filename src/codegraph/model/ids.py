"""Stable symbol identifiers and the codegraph:// URI scheme.

Symbol IDs are engine-independent so overlay data (descriptions, reasons)
survives a backend swap: ``<repo-relative-path>::<qualified-name>``.
"""

from __future__ import annotations

import re
from pathlib import Path

URI_SCHEME = "codegraph://"


def symbol_id(path: str | Path, qualname: str, repo_root: str | Path | None = None) -> str:
    """Build the stable ID for a symbol; paths are stored repo-relative."""
    p = Path(path)
    if repo_root is not None:
        try:
            p = p.relative_to(repo_root)
        except ValueError:
            pass
    return f"{p.as_posix()}::{qualname}"


def library_id(package_name: str) -> str:
    return f"lib::{package_name}"


def slugify(sid: str) -> str:
    """Filesystem-safe slug for a symbol ID (description filenames)."""
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", sid).strip("-").lower()


def to_uri(sid: str) -> str:
    return f"{URI_SCHEME}{sid}"


def from_uri(uri: str) -> str:
    if not uri.startswith(URI_SCHEME):
        raise ValueError(f"not a codegraph URI: {uri!r}")
    return uri[len(URI_SCHEME):]
