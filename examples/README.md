# Example: two addons and their graph

You do not need an ERPForAll project to see `tools/addon-graph.py` work. This folder holds two small addons and the
graph data the tool produces from them. Everything here is invented sample data.

## The two addons (`examples/addons/`)

- `library` (data-only, scaffolded with `tools/new-addon.py library --model library.book`, then extended by hand):
  models `library.book`, `library.author` (one author has many books) and `library.genre` (many to many with books);
  list, form and search views; a window action and a menu per main model; an access CSV; default genres in
  `data/library_data.xml`; two invented authors and books in `demo/library_demo.xml`.
- `library_loans` (depends on `library`): a model `library_loans.loan` pointing at `library.book`; an extension of
  `library.book` with a `loan_ids` field (`models/20_book.toml`, `extend = "library.book"`); a view that inherits the
  book form with an xpath and adds a Loans page; a menu under the library menu; demo data.

`python3 tools/addon-lint.py examples/addons/library --addons-path examples/addons` and the same for `library_loans`
report `0 error(s), 0 warning(s)`.

## Try it (five minutes)

Run these from the root of this repository:

```bash
python3 tools/addon-graph.py --addons-path examples/addons summary
python3 tools/addon-graph.py --addons-path examples/addons model library.book
python3 tools/addon-graph.py --addons-path examples/addons field library.book loan_ids
python3 tools/addon-graph.py --addons-path examples/addons field library.book loans    # exit status 1: not declared
python3 tools/addon-graph.py --addons-path examples/addons impact examples/addons/library/models/10_book.toml
python3 tools/addon-graph.py --addons-path examples/addons context "show the loans of a book on the book form"
```

The committed outputs are in `examples/graph/` (one file per command, each starting with the command line), and the
whole graph as JSON in `examples/graph/graph.json` (format: `docs/addon-graph-format.md`).
`examples/build-graph.sh` regenerates all of it; `tests/test_examples.py` fails if the committed files drift from the tool.

## What to look for

- `model library.book` shows one model written by two addons: defined by `library`, extended by `library_loans`, with
  the field `loan_ids` coming from the extension and a fourth view that is the inherited form.

  ```
  model library.book - Book
    defines by library  examples/addons/library/models/10_book.toml:2
    extends by library_loans  examples/addons/library_loans/models/20_book.toml:2
  ```
- `impact` on the book model file shows what else to look at when you change it: the addon that depends on this one,
  every view, action and access row for the model, and fields in other models that point at it.

  ```
  impact of 1 file(s): addons library; addons that depend on them: library_loans
  field library_loans.loan.book_id (examples/addons/library_loans/models/10_loan.toml:7) points at library.book
  ```
- `field library.book loans` exits with status 1: the field is called `loan_ids`. A name an agent invents fails here,
  before it reaches a view or a call.

## How an agent uses `context`

Before it starts a task, an agent runs `context "<the task in its own words>"` and opens the files it lists, first the
models and fields, then the views, menus and access rows. For "show the loans of a book on the book form" it lands on
`library.book`, the `loan_ids` extension field, the inherited form view and the loan model, each with `path:line`.
Before it writes a model or field name into a view, an access row or a client call it runs `model` or `field`; exit
status 1 means "not declared in these addons". After a change it runs `impact` on the changed files. See
`skills/erpforall-knowledge-graph/SKILL.md`.

## Limits of the sample

The addons are data-only, so there are no `rpc` or `method` nodes and no model-to-model `inherits` edges here; a native
addon with `#[methods]` blocks produces them (see the skill). The graph covers your addons only: `base` and other
framework models are outside it.
