# Schema And Queries

The first SQLite storage module implements these tables: repositories, snapshots, files, nodes, edges, unresolved_references and jobs. Imports and call sites are still represented in JSON extraction output and resolved edges; dedicated tables are still pending.

Logical IDs are stable hashes over normalized path, node kind, qualified name and signature. They should survive blank-line edits where the symbol name and signature remain unchanged, but they do not promise rename or move stability.

Documents, configs and dependencies use the same node table as code symbols. Markdown links become `REFERENCES` edges only when the target path exists. `pyproject.toml` dependency declarations become `DECLARES_DEPENDENCY` edges.

Bounded traversal starts at the seed node with depth zero. Depth 3 means at most three edges away. The query uses a visited set so cycles terminate and reports a truncation flag when node or edge budgets are hit.
