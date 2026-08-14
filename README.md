# codebase-visualizer

Turn any codebase into a **queryable, visualizable code graph**: every function traced to its callers and callees, libraries as separate components, line-level PR diff overlays, linked plain-language component descriptions, and a reasoning log for *why* code exists or changed.

Ships three surfaces over one graph:

1. **CLI** — `codegraph index | trace | query | diff | describe | why | export | ui | doctor`
2. **MCP server** — `search_graph`, `trace_path`, `query_graph`, `get_architecture`, `diff_overlay`, `describe_component`, `set_description`, `record_reason`, `why_trace` (names mirror the codebase-memory-mcp vocabulary)
3. **Isometric map** — a single self-contained HTML file: LOC-scaled 3D blocks zoned by role, animated data-flow dots, drill-downs (`#inside=ID`), request-trace stepping (`#trace=N`), and a PR diff mode with per-component +N/−M badges

Indexing is powered by [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext) (tree-sitter, 26 languages, embedded FalkorDB) behind an adapter seam, so the engine is swappable.

## Install

```bash
pip install codegraphcontext          # engine
pip install codebase-visualizer      # this package (or: pip install -e . from a clone)
```

## Quick start

```bash
cd your-repo
codegraph index                       # build the graph
codegraph trace handle_request        # who calls it, what it calls
codegraph diff main                   # line-level ± per symbol vs main
codegraph ui                          # open the isometric map
codegraph ui --base main              # map with PR diff badges
```

## MCP (Claude Code)

```bash
claude mcp add code-graph -- codegraph mcp-serve --root /path/to/repo
```

## Overlay data (committable)

```
your-repo/.codegraph/
├── descriptions/<symbol>.md   # plain-language component descriptions, cross-linked
└── reasons.jsonl              # why symbols exist / changed, per trace
```

Descriptions carry a content hash; `codegraph index` flags them stale when the underlying symbol changes. `codegraph describe --list-missing` + `--list-stale` drive an agent loop that keeps the whole codebase described.

## Share safety

`codegraph export --format isometric --scrub` scrubs sensitive strings (secrets, cloud identifiers) from the exported map before you share it.

## License

MIT
