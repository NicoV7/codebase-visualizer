# codebase-visualizer

Turn any codebase into a **queryable, visualizable code graph**: every function traced to its callers and callees, libraries as separate components, line-level PR diff overlays, linked plain-language component descriptions, and a reasoning log for *why* code exists or changed.

Ships three surfaces over one graph:

1. **CLI** — `codegraph index | trace | query | diff | describe | why | export | ui | doctor`
2. **MCP server** — `search_graph`, `trace_path`, `query_graph`, `get_architecture`, `diff_overlay`, `describe_component`, `set_description`, `record_reason`, `why_trace` (names mirror the codebase-memory-mcp vocabulary)
3. **3D code city** (default) — a single self-contained WebGL scene: orbit/pan/zoom around LOC-scaled buildings zoned by role, **click any component to expand it in place** into its files, click a file to expand its functions (complexity-tinted), animated data-flow dots, shareable hash state (`#inside=a,b&file=comp:path&trace=N&focus=symbol`), and a PR diff mode with +N/−M badges
4. **2D isometric map** (`--format isometric` / `ui --flat`) — the lightweight no-WebGL fallback with the same zones, flow dots, and trace stepping

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
codegraph ui                          # open the 3D code city
codegraph ui --base main              # city with PR diff badges
codegraph ui --flat                   # 2D isometric map (no WebGL)
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

## Vendored dependencies

The 3D city embeds a prebuilt [three.js](https://github.com/mrdoob/three.js) + OrbitControls bundle (`viz/vendor/three-bundle.min.js`, MIT). Regenerate it with `cd scripts && npm install && node build-vendor.mjs` — node is needed only for that.

## License

MIT (three.js is also MIT; its notice ships in the vendored bundle banner)
