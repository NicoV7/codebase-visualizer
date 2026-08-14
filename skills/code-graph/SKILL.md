---
id: code-graph
title: Query, trace, and visualize a codebase with the code-graph tools
category: SKILLS
domain: code-graph
when_to_use: >
  When asked to visualize a codebase, map its architecture, trace who calls a
  function (or what it calls), show the blast radius or line-level impact of a
  PR, describe a component, or record why code exists or changed.
---

# code-graph

Use the `code-graph` MCP tools (or the `codegraph` CLI) instead of grepping when the question is structural.

## Steps

1. Not indexed yet? Run `index_repo` (CLI: `codegraph index`) once; re-run with `incremental=true` after changes.
2. "Who calls X / what does X call" → `trace_path(function_name, direction=in|out|both)`.
3. "Show the architecture / visualize the codebase" → `get_architecture`, or `codegraph ui` for the interactive 3D code city — click a component to expand its files in place, click a file for its functions; `--base main` adds PR diff badges; `--flat` gives the 2D no-WebGL map. Share exact views via the hash: `#inside=a,b&file=comp:path&trace=N&focus=symbolId`.
4. "What changed in this PR and what does it touch" → `diff_overlay(base)`: per-symbol added/removed line numbers plus hunks; combine with inbound `trace_path` on changed symbols for blast radius.
5. Arbitrary structure questions → `query_graph` with Cypher (nodes: Function, Class, File, Module; edges: CALLS, IMPORTS, CONTAINS).

## Descriptions and reasons

- Before explaining a component, check `describe_component(symbol_id)`; write missing ones with `set_description` following `describe-style.md` in this directory. Use `list_undescribed` to drive a describe-the-codebase loop.
- When you add, change, or explain non-obvious code, log the why: `record_reason(symbol_id, why, kind=exists|changed)`. Read history with `why_trace`.

## What good looks like

An answer that cites graph facts (callers, spans, edge counts) rather than guesses, links components by their `codegraph://` IDs, and leaves behind descriptions and reasons the next agent can reuse.
