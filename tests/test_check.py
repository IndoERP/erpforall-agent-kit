import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from _load import ROOT
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("check", ROOT / "scripts" / "check.py")
check = importlib.util.module_from_spec(spec)
sys.modules["check"] = check
spec.loader.exec_module(check)

GOOD = """---
name: erpforall-demo
description: Demo skill for tests. Use when a test needs a valid skill file with a description.
---

# Demo

Read `views.md` first.

## Sources

- docs/addon-guide/views.md
- addons/x/manifest.toml
"""


class CheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        (self.src / "docs/addon-guide").mkdir(parents=True)
        (self.src / "docs/addon-guide/views.md").write_text("x")
        (self.src / "addons/x").mkdir(parents=True)
        (self.src / "addons/x/manifest.toml").write_text("x")
        self.skills = self.root / "skills"
        self.dir = self.skills / "erpforall-demo"
        self.dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text):
        (self.dir / "SKILL.md").write_text(text)

    def errs(self, source=True):
        return check.check_skill(self.dir, self.src if source else None)

    def test_good_skill(self):
        self.write(GOOD)
        self.assertEqual(self.errs(), [])

    def test_missing_frontmatter(self):
        self.write("# Demo\n")
        self.assertIn("frontmatter", self.errs()[0])

    def test_name_must_match_directory_and_format(self):
        self.write(GOOD.replace("name: erpforall-demo", "name: Other_Name"))
        msgs = " ".join(self.errs())
        self.assertIn("does not match the directory", msgs)
        self.assertIn("lowercase", msgs)

    def test_description_length(self):
        self.write(GOOD.replace("Demo skill for tests. Use when a test needs a valid skill file with a description.", "x" * 1025))
        self.assertIn("1025 characters", " ".join(self.errs()))
        self.write(GOOD.replace("Demo skill for tests. Use when a test needs a valid skill file with a description.", "short"))
        self.assertIn("too short", " ".join(self.errs()))

    def test_sources_section_required_last_and_nonempty(self):
        self.write(GOOD.split("## Sources")[0])
        self.assertIn("## Sources", " ".join(self.errs()))
        self.write(GOOD + "\n## After\n")
        self.assertIn("last section", " ".join(self.errs()))
        self.write(GOOD.split("- docs")[0])
        self.assertIn("empty", " ".join(self.errs()))

    def test_source_paths_must_exist_when_checked(self):
        self.write(GOOD.replace("addons/x/manifest.toml", "addons/y/manifest.toml"))
        self.assertIn("does not exist", " ".join(self.errs()))
        self.assertEqual(self.errs(source=False), [])  # not verified without --source

    def test_absolute_or_escaping_sources_refused(self):
        self.write(GOOD.replace("addons/x/manifest.toml", "../outside.md"))
        self.assertIn("repo-relative", " ".join(self.errs()))

    def test_named_guide_page_must_exist(self):
        self.write(GOOD.replace("`views.md`", "`ghost.md`"))
        self.assertIn("ghost.md", " ".join(self.errs()))

    def test_hygiene(self):
        self.write(GOOD.replace("Read", "Mail me at a.person@example.org or use build.internal. Read"))
        msgs = " ".join(self.errs())
        self.assertIn("a.person@example.org", msgs)
        self.assertIn("build.internal", msgs)

    def test_main_exit_codes_and_extra_forbid(self):
        self.write(GOOD)
        forbid = self.root / "forbid.txt"
        forbid.write_text("valid skill\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check.main(["--skills", str(self.skills), "--source", str(self.src)]), 0)
            self.assertEqual(check.main(["--skills", str(self.skills), "--source", str(self.src), "--forbid", str(forbid)]), 1)
            self.assertEqual(check.main(["--skills", str(self.root / "none")]), 2)
            self.assertEqual(check.main(["--skills", str(self.skills), "--source", str(self.root / "nope")]), 2)

    def test_repository_skills_pass_without_source(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check.main([]), 0)


if __name__ == "__main__":
    unittest.main()
