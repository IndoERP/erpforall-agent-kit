---
name: erpforall-knowledge-graph
description: Look up ERPForAll models, fields, methods, RPC exposure, views, access rows and dependencies with source locations. Use before writing against a model or field, extending another addon, or assessing the impact of a change in an addon or the framework.
---

# Query the ERPForAll knowledge graph

Run `erpforall-addon-graph` from the project root. The script in the kit is `tools/addon-graph.py` and requires Python 3.10+ with the standard library.

1. Run `erpforall-addon-graph context "<task>"` and read the matching source locations. Repeat `--addons-path DIR` before the command to include each addon directory.
2. Run `erpforall-addon-graph model <name>` before extending a model. Use `erpforall-addon-graph field <model> <field>` before naming a field in a view, action or client call. Exit 1 means the query missed the indexed sources.
3. From the framework root the graph includes the core automatically. In a separate addon project use, for example, `erpforall-addon-graph --framework-root ../ERPForAll field res.users login`. Include framework addons through an additional `--addons-path` when you need their extensions too.
4. Use `erpforall-addon-graph model res.users --json` to inspect a method's `sources`, including inherited core registrations, addon overrides and the invocation line of supported local method macros. The `rpc` and `effect` fields describe exposure across the indexed declarations.
5. Run `erpforall-addon-graph impact <changed file>...` from the same root to find affected models, references and addon packages. For addon changes, run addon lint on the affected addons and verify installation with the framework loader.
6. Run `erpforall-addon-graph summary --json` for counts and the full list of parser diagnostics. Investigate ambiguous, external or unsupported Rust targets at the reported file and line before relying on a missing result.

The index reads Rust declarations, TOML models, XML records, access CSVs and manifests. With the framework sources it also reads registry fields, module metadata, ORM registrations and core RPCs. Field lookups include inherited fields and use core declarations for audit fields on eligible models. Macro tracing supports local single-arm method templates with identifier arguments. Runtime overlays, database customizations and arbitrary Rust macro expansion require verification in the loaded registry.

Use `erpforall-addon-graph export` for sorted JSON nodes and edges. The kit includes a standalone addon example in `examples/graph/`.

## Sources

- crates/erp-registry/src/compose.rs
- crates/erp-registry/src/keys.rs
- crates/erp-modules/src/base_models.rs
- crates/erp-data/src/model_data.rs
- crates/erp-orm/src/records.rs
- crates/erp-orm/src/dispatch.rs
- crates/erp-orm/src/rpc/core.rs
- addons/base/src/res_users.rs
- addons/account/src/reconcile/guards.rs
- addons/sample_library/manifest.toml
- addons/sample_library/models/20_book.toml
- addons/sample_library/security/ir.access.csv
