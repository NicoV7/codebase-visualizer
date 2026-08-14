---
symbol_id: codegraph/mcp/server.py::build_server
hash_at_write: 502692a99575c9af
links: []
---

Builds the code-graph MCP server: 11 tools over one CodeGraphService.

1. Wraps engine queries (search, trace, Cypher)
2. Merges overlay data into responses
3. Stores descriptions/reasons written by the calling agent

Constraint: this server stores descriptions, never generates them — generation stays in the agent so no API keys live here.
