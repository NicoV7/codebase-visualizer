"""codegraph CLI: index, trace, query, diff, describe, why, export, ui, doctor."""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

import typer

from codegraph.engine.protocol import EngineError
from codegraph.service import CodeGraphService

app = typer.Typer(help="Code graph: index, trace, visualize, and annotate any codebase.")


def _service(root: str = ".") -> CodeGraphService:
    return CodeGraphService(root)


def _fail(exc: Exception) -> None:
    typer.secho(f"error: {exc}", fg="red", err=True)
    raise typer.Exit(1)


@app.command()
def index(
    root: str = typer.Argument("."),
    incremental: bool = typer.Option(False, "--incremental", help="Refresh instead of full index"),
):
    """Index (or refresh) a repository into the code graph."""
    try:
        stats = _service(root).index(incremental=incremental)
    except EngineError as exc:
        _fail(exc)
    typer.echo("\n".join(stats["output_tail"]))
    if stats["stale_descriptions"]:
        typer.secho(
            f"{len(stats['stale_descriptions'])} stale description(s): "
            + ", ".join(stats["stale_descriptions"][:5]),
            fg="yellow",
        )


@app.command()
def trace(
    function: str,
    direction: str = typer.Option("both", help="in | out | both"),
    depth: int = typer.Option(3),
    root: str = typer.Option(".", "--root"),
):
    """Trace callers (in) and callees (out) of a function."""
    try:
        rows = _service(root).trace(function, direction=direction, depth=depth)
    except EngineError as exc:
        _fail(exc)
    if not rows:
        typer.echo(f"no call paths found for {function!r} (is the repo indexed?)")
        raise typer.Exit(0)
    for row in rows:
        arrow = "◀" if row["direction"] == "in" else "▶"
        typer.echo(f"{arrow} {row['hops']} hop(s)  {row['name']}  {row.get('path','')}:{row.get('line','')}")


@app.command()
def query(cypher: str, root: str = typer.Option(".", "--root")):
    """Run a raw Cypher query against the graph."""
    try:
        typer.echo(json.dumps(_service(root).engine.query(cypher), indent=1))
    except EngineError as exc:
        _fail(exc)


@app.command()
def diff(
    base: str = typer.Argument(..., help="Base ref, e.g. main"),
    head: str = typer.Argument("HEAD"),
    root: str = typer.Option(".", "--root"),
):
    """Line-level PR overlay: per-symbol +/− lines between two refs."""
    try:
        overlay = _service(root).diff(base, head)
    except Exception as exc:  # git or engine failure — both fatal here
        _fail(exc)
    for nd in sorted(overlay.per_node, key=lambda d: -(len(d.added_lines) + len(d.removed_lines))):
        typer.echo(f"+{len(nd.added_lines)} −{len(nd.removed_lines)}  {nd.symbol_id}")
    if overlay.unmapped_files:
        typer.secho(f"unmapped (no indexed symbols): {', '.join(overlay.unmapped_files)}", fg="yellow")


@app.command()
def describe(
    symbol: str = typer.Argument(None),
    list_stale: bool = typer.Option(False, "--list-stale"),
    list_missing: bool = typer.Option(False, "--list-missing"),
    body_file: Path = typer.Option(None, "--body-file", help="Markdown body to store"),
    root: str = typer.Option(".", "--root"),
):
    """Read or write a component description (write via --body-file)."""
    svc = _service(root)
    if list_stale:
        for d in svc.descriptions.mark_stale(svc._symbol_hashes()):
            typer.echo(d.symbol_id)
        return
    if list_missing:
        ids = [n.id for n in svc.graph().nodes if n.kind in ("function", "class")]
        for sid in svc.descriptions.undescribed(ids):
            typer.echo(sid)
        return
    if symbol is None:
        _fail(ValueError("pass a symbol id, --list-stale, or --list-missing"))
    if body_file is not None:
        typer.echo(svc.describe(symbol, body_file.read_text()))
        return
    desc = svc.descriptions.read(symbol)
    if desc is None:
        typer.echo(f"no description for {symbol}")
        raise typer.Exit(1)
    typer.echo(desc.body)


@app.command()
def why(
    symbol_or_trace: str,
    record: str = typer.Option(None, "--record", help="Record a new reason instead of reading"),
    kind: str = typer.Option("exists", help="exists | changed"),
    root: str = typer.Option(".", "--root"),
):
    """Read (or --record) the reasoning log for a symbol or trace id."""
    svc = _service(root)
    if record:
        reason = svc.record_reason(symbol_id=symbol_or_trace, why=record, kind=kind, source="manual")
        typer.echo(f"recorded {reason.id}")
        return
    entries = svc.why(symbol_or_trace)
    if not entries:
        typer.echo("no reasons recorded")
        raise typer.Exit(0)
    for r in entries:
        typer.echo(f"[{r.created_at}] ({r.kind}/{r.source}) {r.why}")


@app.command("export")
def export_cmd(
    fmt: str = typer.Option("graphjson", "--format", help="graphjson | isometric"),
    out: str = typer.Option(None, "--out"),
    base: str = typer.Option(None, "--base", help="Include diff overlay vs this ref (isometric)"),
    scrub: bool = typer.Option(False, "--scrub", help="Share-safety scrub of sensitive strings"),
    root: str = typer.Option(".", "--root"),
):
    """Export the graph as JSON or a self-contained isometric HTML map."""
    svc = _service(root)
    try:
        if fmt == "graphjson":
            path = svc.export_graphjson(out or ".codegraph/graph.json")
        elif fmt == "isometric":
            path = svc.export_isometric(out or ".codegraph/map.html", base=base, scrub=scrub)
        else:
            raise ValueError(f"unknown format {fmt!r}")
    except Exception as exc:
        _fail(exc)
    typer.echo(path)


@app.command()
def ui(
    root: str = typer.Option(".", "--root"),
    base: str = typer.Option(None, "--base"),
    no_open: bool = typer.Option(False, "--no-open"),
):
    """Export the isometric map and open it in the browser."""
    svc = _service(root)
    try:
        path = svc.export_isometric(str(Path(root) / ".codegraph" / "map.html"), base=base)
    except Exception as exc:
        _fail(exc)
    typer.echo(path)
    if not no_open:
        webbrowser.open(f"file://{Path(path).resolve()}")


@app.command()
def doctor(root: str = typer.Option(".", "--root")):
    """Check the engine, overlay stores, and template."""
    try:
        for line in _service(root).doctor():
            typer.echo(line)
    except EngineError as exc:
        _fail(exc)


@app.command("mcp-serve")
def mcp_serve(root: str = typer.Option(".", "--root")):
    """Run the code-graph MCP server on stdio."""
    from codegraph.mcp.server import build_server

    build_server(root).run()


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
