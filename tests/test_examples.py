"""The committed sample graph must be exactly what the tool produces from the example addons."""
import filecmp
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _load import ROOT, load

lint = load("addon-lint")


class ExampleTests(unittest.TestCase):
    def test_build_graph_reproduces_the_committed_files_byte_for_byte(self):
        if shutil.which("bash") is None:
            self.skipTest("bash is not available")
        tmp = Path(tempfile.mkdtemp(prefix="exgraph"))
        try:
            r = subprocess.run(["bash", str(ROOT / "examples/build-graph.sh"), str(tmp)], capture_output=True, text=True,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(r.returncode, 0, r.stderr)
            committed = sorted(p.name for p in (ROOT / "examples/graph").iterdir())
            self.assertEqual(committed, sorted(p.name for p in tmp.iterdir()))
            self.assertGreaterEqual(len(committed), 7)
            for name in committed:
                self.assertTrue(filecmp.cmp(ROOT / "examples/graph" / name, tmp / name, shallow=False), f"{name} drifted: run examples/build-graph.sh")
                if name.endswith(".txt"):
                    first = (ROOT / "examples/graph" / name).read_text().splitlines()[0]
                    self.assertTrue(first.startswith("$ python3 tools/addon-graph.py --addons-path examples/addons "), name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_export_is_sorted_and_complete(self):
        d = json.loads((ROOT / "examples/graph/graph.json").read_text())
        self.assertEqual(d["format"], "addon-graph/1")
        self.assertEqual(d["not_understood"], [])
        keys = [(n["kind"], n["name"]) for n in d["nodes"]]
        self.assertEqual(keys, sorted(keys))
        kinds = {n["kind"] for n in d["nodes"]}
        self.assertTrue({"addon", "model", "field", "view", "menu", "action", "access", "record"} <= kinds)
        ekinds = {e["kind"] for e in d["edges"]}
        self.assertTrue({"depends_on", "defines", "extends", "has_field", "relates_to", "refers_to", "uses_field", "opens",
                         "child_of", "inherits"} <= ekinds)
        names = {f"{n['kind']}:{n['name']}" for n in d["nodes"]}
        for e in d["edges"]:
            self.assertIn(e["to"], names)
            self.assertIn(e["from"], names)

    def test_example_addons_lint_clean(self):
        for addon in ("library", "library_loans"):
            findings = lint.lint(ROOT / "examples/addons" / addon, [ROOT / "examples/addons"])
            self.assertEqual([f for f in findings if f.level in ("E", "W")], [], addon)


if __name__ == "__main__":
    unittest.main()
