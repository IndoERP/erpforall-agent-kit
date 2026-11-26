# `addon-graph.py export`: the JSON format

`python3 tools/addon-graph.py --addons-path <dir> export` prints the whole graph of your addons as JSON. It is
sorted and uses the paths supplied to the tool. Use relative roots for a portable export. A worked sample is
`examples/graph/graph.json`.

```json
{
 "format": "addon-graph/1",
 "nodes": [{"kind": "model", "name": "library.book", "file": "examples/addons/library/models/10_book.toml", "line": 2}],
 "edges": [{"kind": "has_field", "from": "model:library.book", "to": "field:library.book.name", "file": "...", "line": 7}],
 "not_understood": [{"file": "...", "line": 1, "reason": "..."}]
}
```

- `nodes` are sorted by `kind`, then `name`. Kinds: `addon`, `model`, `field` (`<model>.<field>`), `rpc` and `method`
  (`<model>.<method>`, native declarations and indexed core registrations), `view`, `action`, `menu`, `access` and `record` (ids are
  `<addon>.<id>`). `file` and `line` point at the declaration (for a model, its defining declaration).
- `edges` are sorted by `kind`, `from`, `to`, `file`, `line`. `from` and `to` are `<kind>:<name>`. Kinds:
  `depends_on` (addon to addon), `defines` and `extends` (addon to model), `has_field`, `has_method`, `relates_to`
  (field to its comodel), `inherits` (model to model, or view to the view it inherits), `refers_to` (view, action,
  access row or record to a model), `uses_field` (view to a field its arch shows), `opens` (menu to action), `child_of`
  (menu to parent menu). `file` and `line` are where the source says it.
- From the ERPForAll root, or with `--framework-root DIR`, the graph includes core model declarations, inherited
  base fields, applicable audit and row-version fields, ORM method registrations and RPC declarations. Core addon
  descriptors supplement the manifest addons. The summary's addon count counts manifests.
- A method node represents the directly indexed declarations on its model. Each implementation or exposure contributes
  a `has_method` edge at its source. A supported local macro also contributes an edge at the invocation. For an
  inherited method and its complete list of source locations use `model <name> --json`.
- Targets outside the indexed roots are omitted from exported edges. Standalone addon indexes can therefore have
  references whose targets appear only when a framework or additional addon directory is included.
- `not_understood` lists what the readers could not parse, with the reason. It is empty for the examples.
- A change of the layout bumps `format`.
