#!/usr/bin/env bash
# Regenerate the sample graph data of the two example addons (examples/graph/). Run from anywhere:
#   examples/build-graph.sh [OUTPUT_DIR]      # default: examples/graph
# Every text file starts with the exact command line that produced it. tests/test_examples.py runs this into a
# temporary directory and compares the result byte for byte with the committed files.
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-examples/graph}"
mkdir -p "$out"
tool="python3 tools/addon-graph.py --addons-path examples/addons"

run() { # file-name, arguments of the tool (quoted as they appear in the first line)
  local name="$1"; shift
  local cmd="$tool"
  local arg
  for arg in "$@"; do
    case "$arg" in *" "*) cmd+=" \"$arg\"" ;; *) cmd+=" $arg" ;; esac
  done
  { echo "\$ $cmd"; python3 tools/addon-graph.py --addons-path examples/addons "$@" || true; } > "$out/$name"
}

run summary.txt summary
run model-library.book.txt model library.book
run model-library_loans.loan.txt model library_loans.loan
run field.txt field library.book loan_ids
run impact.txt impact examples/addons/library/models/10_book.toml
run context.txt context "show the loans of a book on the book form"
python3 tools/addon-graph.py --addons-path examples/addons export > "$out/graph.json"
