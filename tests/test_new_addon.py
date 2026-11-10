import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from _load import load

new_addon = load("new-addon")
addon_lint = load("addon-lint")


class ScaffoldTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_layout_is_the_data_only_layout(self):
        new_addon.scaffold(self.dest, "my_tags")
        files = sorted(p.relative_to(self.dest / "my_tags").as_posix() for p in (self.dest / "my_tags").rglob("*") if p.is_file())
        self.assertEqual(files, ["manifest.toml", "models/10_item.toml", "security/ir.access.csv", "views/my_tags_views.xml"])

    def test_scaffold_passes_the_lint_cleanly(self):
        new_addon.scaffold(self.dest, "my_tags", model="my_tags.tag", author='A "quoted" <name>', summary="S & T")
        findings = [f for f in addon_lint.lint(self.dest / "my_tags") if f.level == "E"]
        self.assertEqual(findings, [])

    def test_manifest_and_access_rows(self):
        new_addon.scaffold(self.dest, "my_tags")
        manifest = (self.dest / "my_tags/manifest.toml").read_text()
        self.assertIn('depends = ["base"]', manifest)
        self.assertIn('"views/my_tags_views.xml"', manifest)
        access = (self.dest / "my_tags/security/ir.access.csv").read_text().splitlines()
        self.assertEqual(access[0], "id,name,model_id/id,group_id/id,operation,domain")
        self.assertIn("my_tags.model_my_tags_item,base.group_user,crud,", access[1])
        self.assertTrue((self.dest / "my_tags/views/my_tags_views.xml").read_text().startswith('<?xml version="1.0" encoding="utf-8"?>\n<erp>'))

    def test_rejects_bad_names(self):
        for bad in ("my-addon", "", "a b", "x" * 257):
            with self.assertRaises(ValueError):
                new_addon.scaffold(self.dest, bad)
        with self.assertRaises(ValueError):
            new_addon.scaffold(self.dest, "ok_name", model="NoDots")

    def test_refuses_existing_nonempty_directory(self):
        (self.dest / "taken").mkdir()
        (self.dest / "taken" / "x").write_text("x")
        with self.assertRaises(FileExistsError):
            new_addon.scaffold(self.dest, "taken")

    def test_cli_returns_1_on_error_and_0_on_success(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(new_addon.main(["bad-name", "--dest", str(self.dest)]), 1)
            self.assertEqual(new_addon.main(["good_name", "--dest", str(self.dest)]), 0)


if __name__ == "__main__":
    unittest.main()
