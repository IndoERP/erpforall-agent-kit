# `addon-graph.py export`: the JSON format

`python3 tools/addon-graph.py --addons-path <dir> export` prints the whole graph of your addons as JSON. It is
sorted and contains no times or absolute paths, so the same files give the same bytes. A worked sample is
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
  (`<model>.<method>`, native Rust addons only), `view`, `action`, `menu`, `access` and `record` (ids are
  `<addon>.<id>`). `file` and `line` point at the declaration (for a model, its defining declaration).
- `edges` are sorted by `kind`, `from`, `to`, `file`, `line`. `from` and `to` are `<kind>:<name>`. Kinds:
  `depends_on` (addon to addon), `defines` and `extends` (addon to model), `has_field`, `has_method`, `relates_to`
  (field to its comodel), `inherits` (model to model, or view to the view it inherits), `refers_to` (view, action,
  access row or record to a model), `uses_field` (view to a field its arch shows), `opens` (menu to action), `child_of`
  (menu to parent menu). `file` and `line` are where the source says it.
- An edge whose target is not defined by these addons (`base`, `res.partner`, implicit fields such as `create_uid`)
  is left out; the framework's own models are not part of the graph.
- `not_understood` lists what the readers could not parse, with the reason. It is empty for the examples.
- A change of the layout bumps `format`.
