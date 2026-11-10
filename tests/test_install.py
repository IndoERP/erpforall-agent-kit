import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"
SKILLS = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())


class InstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "home"
        self.proj = Path(self._tmp.name) / "proj"
        self.home.mkdir()
        self.proj.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def run_install(self, *args, ok=True):
        env = {**os.environ, "HOME": str(self.home)}
        r = subprocess.run(["bash", str(INSTALL), *args], capture_output=True, text=True, env=env, cwd=self.proj)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def tree(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))

    def test_dry_run_changes_nothing(self):
        r = self.run_install("--agent", "all", "--dry-run")
        self.assertIn("would:", r.stdout)
        self.assertEqual(self.tree(), [])

    def test_user_install_links_all_skills_per_agent(self):
        self.run_install("--agent", "claude", "--agent", "codex", "--agent", "antigravity", "--agent", "gemini")
        for base in (".claude/skills", ".agents/skills", ".gemini/config/skills", ".gemini/skills"):
            for name in SKILLS:
                link = self.home / base / name
                self.assertTrue(link.is_symlink(), link)
                self.assertEqual(os.readlink(link), str(ROOT / "skills" / name))
                self.assertTrue((link / "SKILL.md").is_file())
        for cmd in ("erpforall-new-addon", "erpforall-addon-lint"):
            self.assertTrue((self.home / ".local/bin" / cmd).is_symlink())

    def test_idempotent(self):
        self.run_install("--agent", "claude")
        before = self.tree()
        r = self.run_install("--agent", "claude")
        self.assertEqual(self.tree(), before)
        self.assertIn("already linked", r.stdout)

    def test_never_overwrites_unrelated_folder_or_file(self):
        mine = self.home / ".claude/skills" / SKILLS[0]
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my own skill")
        tool = self.home / ".local/bin/erpforall-addon-lint"
        tool.parent.mkdir(parents=True)
        tool.write_text("#!/bin/sh\necho mine\n")
        r = self.run_install("--agent", "claude")
        self.assertEqual((mine / "SKILL.md").read_text(), "my own skill")
        self.assertEqual(tool.read_text(), "#!/bin/sh\necho mine\n")
        self.assertIn("left untouched", r.stdout)
        self.assertIn("not this kit's tool", r.stdout)
        self.run_install("--uninstall", "--agent", "claude")
        self.assertEqual((mine / "SKILL.md").read_text(), "my own skill")
        self.assertTrue(tool.exists())
        self.assertFalse((self.home / ".claude/skills" / SKILLS[1]).exists())

    def test_foreign_symlink_needs_force(self):
        other = Path(self._tmp.name) / "elsewhere"
        other.mkdir()
        link = self.home / ".claude/skills" / SKILLS[0]
        link.parent.mkdir(parents=True)
        link.symlink_to(other)
        r = self.run_install("--agent", "claude")
        self.assertEqual(os.readlink(link), str(other))
        self.assertIn("use --force", r.stdout)
        self.run_install("--agent", "claude", "--force")
        self.assertEqual(os.readlink(link), str(ROOT / "skills" / SKILLS[0]))

    def test_copy_mode_and_uninstall(self):
        self.run_install("--agent", "codex", "--copy", "--no-tools")
        d = self.home / ".agents/skills" / SKILLS[0]
        self.assertTrue(d.is_dir() and not d.is_symlink())
        self.assertTrue((d / ".erpforall-agent-kit").is_file())
        self.assertTrue((d / "SKILL.md").is_file())
        self.run_install("--agent", "codex", "--copy", "--no-tools")  # refresh in place
        self.run_install("--uninstall", "--agent", "codex", "--no-tools")
        self.assertEqual(self.tree(), [".agents", ".agents/skills"])

    def test_copied_tools_are_removed_only_when_identical(self):
        self.run_install("--agent", "claude", "--copy")
        lint = self.home / ".local/bin/erpforall-addon-lint"
        self.assertTrue(lint.is_file() and not lint.is_symlink())
        self.assertTrue(os.access(lint, os.X_OK))
        self.run_install("--uninstall", "--agent", "claude")
        self.assertFalse(lint.exists())

    def test_project_scope(self):
        self.run_install("--agent", "codex", "--agent", "gemini", "--scope", "project")
        self.assertTrue((self.proj / ".agents/skills" / SKILLS[0]).is_symlink())
        self.assertTrue((self.proj / ".gemini/skills" / SKILLS[0]).is_symlink())
        self.assertEqual(self.tree(), [])  # nothing under HOME, tools skipped

    def test_agents_md_block_is_added_refreshed_and_removed(self):
        agents = self.proj / "AGENTS.md"
        agents.write_text("# My project\n\nKeep this.\n")
        self.run_install("--agent", "codex", "--scope", "project", "--agents-md")
        text = agents.read_text()
        self.assertTrue(text.startswith("# My project\n\nKeep this.\n"))
        self.assertEqual(text.count("erpforall-agent-kit:begin"), 1)
        self.assertIn(f"{ROOT}/skills/erpforall-views/SKILL.md", text)
        self.assertNotIn("{{KIT}}", text)
        self.run_install("--agent", "codex", "--scope", "project", "--agents-md")
        self.assertEqual(agents.read_text(), text)
        self.run_install("--uninstall", "--agent", "codex", "--scope", "project", "--agents-md")
        self.assertEqual(agents.read_text().strip(), "# My project\n\nKeep this.")

    def test_usage_errors(self):
        self.assertEqual(self.run_install(ok=False).returncode, 2)
        self.assertEqual(self.run_install("--agent", "vim", ok=False).returncode, 2)
        self.assertEqual(self.run_install("--agent", "claude", "--scope", "x", ok=False).returncode, 2)

    def test_generated_packaging_is_current(self):
        r = subprocess.run(["python3", "-I", str(ROOT / "scripts/build-packaging.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
