import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from _load import load

levels = load("test-levels")


def checkout(folder: Path) -> Path:
    """A git repository that looks like a framework checkout, with one commit."""
    (folder / "scripts").mkdir()
    (folder / "scripts" / "check.sh").write_text("#!/bin/sh\n")
    (folder / "Cargo.toml").write_text("[workspace]\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    for argv in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "first"]):
        subprocess.run(["git", "-C", str(folder), *argv], check=True, env=env, capture_output=True)
    return folder


class PlanTest(unittest.TestCase):
    def plan(self, level, **over):
        options = {"base": "origin/main", "web": False, "client_tests": [], "deploy": False, "fast": False, "threads": None, **over}
        return levels.plan(level, **options)

    def test_basic_checks_what_changed_without_a_database_and_can_deploy(self):
        steps = self.plan("basic", deploy=True)
        self.assertEqual([s.command for s in steps], ["scripts/check.sh --affected origin/main", "scripts/install.sh --rebuild"])
        self.assertFalse(any(s.database for s in steps))
        self.assertEqual(self.plan("basic", deploy=True, fast=True)[-1].command, "scripts/install.sh --rebuild --fast")
        self.assertEqual([s.name for s in self.plan("basic", web=True)], ["check", "web-typecheck"])

    def test_normal_tests_the_affected_packages_and_the_changed_client_tests(self):
        steps = self.plan("normal", web=True, client_tests=["../addons/x/static/tests/a.test.ts"], threads=2)
        self.assertEqual([s.name for s in steps], ["check-and-tests", "web-typecheck", "web-tests"])
        self.assertEqual(steps[0].command, "scripts/check.sh --affected origin/main --tests")
        self.assertTrue(steps[0].database)
        self.assertEqual(steps[0].env, {"NEXTEST_TEST_THREADS": "2"})
        self.assertTrue(steps[2].command.endswith("pnpm exec vitest run ../addons/x/static/tests/a.test.ts"))
        # nothing of the client changed: no client step at all
        self.assertEqual([s.name for s in self.plan("normal")], ["check-and-tests"])

    def test_advanced_is_the_whole_workspace_and_the_whole_client_suite(self):
        steps = self.plan("advanced")
        self.assertEqual([s.name for s in steps], ["check-and-tests", "web-typecheck", "web-tests"])
        self.assertEqual(steps[0].command, "scripts/check.sh --tests")
        self.assertTrue(steps[2].command.endswith("pnpm run test"))
        self.assertEqual(self.plan("advanced", deploy=True)[-1].name, "deploy")

    def test_an_unknown_level_is_refused(self):
        with self.assertRaises(ValueError):
            self.plan("quick")


class HelpersTest(unittest.TestCase):
    def test_a_database_password_never_survives(self):
        self.assertEqual(levels.redact("at postgres://erp:s3cret@127.0.0.1:5432/x and postgresql://a:b@h/y"),
                         "at postgres://erp:***@127.0.0.1:5432/x and postgresql://a:***@h/y")
        self.assertEqual(levels.redact("postgres://erp@localhost/x"), "postgres://erp@localhost/x")

    def test_environment_failures_are_named(self):
        self.assertIn("--threads 2", levels.classify("db error: out of shared memory (53200)"))
        self.assertIn("stop editing", levels.classify("NodeDigest(... artifact changed during lifecycle operation)"))
        self.assertIsNone(levels.classify("assertion `left == right` failed"))

    def test_changed_files_select_client_tests_and_addons_to_upgrade(self):
        changed = ["addons/sale/views/sale_views.xml", "addons/sale/src/order.rs", "addons/hr/manifest.toml",
                   "addons/reporting/static/tests/report.test.ts", "web/tests/shell.test.ts", "docs/install.md"]
        self.assertEqual(levels.changed_client_tests(changed), ["../addons/reporting/static/tests/report.test.ts", "tests/shell.test.ts"])
        self.assertEqual(levels.changed_data_addons(changed), ["hr", "sale"])

    def test_a_level_is_satisfied_by_itself_or_a_higher_one_on_a_clean_tree(self):
        run = lambda level, verdict="passed", clean=True: {"level": level, "verdict": verdict, "clean_tree": clean}
        self.assertTrue(levels.satisfied([run("advanced")], "normal"))
        self.assertFalse(levels.satisfied([run("basic")], "normal"))
        self.assertFalse(levels.satisfied([run("normal", "failed"), run("normal", clean=False), run("normal", "invalid")], "normal"))

    def test_preflight_names_what_is_missing(self):
        steps = levels.plan("normal", base="origin/main", web=False, client_tests=[], deploy=False, fast=False, threads=None)
        problems = levels.preflight(steps, {}, {"nextest": "not available"})
        self.assertEqual(len(problems), 2)
        self.assertIn("DATABASE_URL", problems[0])
        self.assertIn("cargo-nextest", problems[1])
        self.assertEqual(levels.preflight(steps, {"DATABASE_URL": "x"}, {"nextest": "cargo-nextest 0.9"}), [])
        basic = levels.plan("basic", base="origin/main", web=False, client_tests=[], deploy=True, fast=False, threads=None)
        self.assertEqual(levels.preflight(basic, {}, {"nextest": "not available"}), [])


class RunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "erpforall"
        self.root.mkdir()
        checkout(self.root)
        self.out = Path(self._tmp.name) / "runs"

    def tearDown(self):
        self._tmp.cleanup()

    def run_level(self, runner, level="normal"):
        steps = levels.plan(level, base="origin/main", web=True, client_tests=[], deploy=False, fast=False, threads=None)
        with contextlib.redirect_stdout(io.StringIO()):
            return levels.execute(level, steps, self.root, self.out, {}, "origin/main", runner=runner)

    def test_a_passing_run_writes_a_receipt_the_status_accepts(self):
        def runner(step, root, log, environ):
            log.write_text("ok\n")
            return 0
        receipt = self.run_level(runner)
        self.assertEqual((receipt["verdict"], receipt["clean_tree"]), ("passed", True))
        self.assertEqual([s["name"] for s in receipt["steps"]], ["check-and-tests", "web-typecheck"])
        found = levels.receipts(self.out, receipt["revision"])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["steps"][0]["command"], "scripts/check.sh --affected origin/main --tests")
        self.assertTrue(levels.satisfied(found, "basic"))
        self.assertFalse(levels.satisfied(found, "advanced"))
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            code = levels.main(["status", "--root", str(self.root), "--out", str(self.out), "--require", "normal"])
        self.assertEqual(code, 0, shown.getvalue())

    def test_a_failure_stops_the_run_and_an_environment_cause_is_recorded(self):
        calls = []

        def runner(step, root, log, environ):
            calls.append(step.name)
            log.write_text("db error: out of shared memory\n")
            return 101
        receipt = self.run_level(runner)
        self.assertEqual(receipt["verdict"], "failed")
        self.assertEqual(calls, ["check-and-tests"])
        self.assertIn("--threads 2", receipt["steps"][0]["environment"])

    def test_a_tree_that_changes_under_the_tests_makes_the_run_invalid(self):
        def runner(step, root, log, environ):
            log.write_text("ok\n")
            (root / "Cargo.toml").write_text("[workspace]\nmembers = []\n")
            return 0
        receipt = self.run_level(runner)
        self.assertEqual(receipt["verdict"], "invalid")
        self.assertIn("working tree changed", receipt["invalid"])
        self.assertFalse(levels.satisfied(levels.receipts(self.out, receipt["revision"]), "basic"))

    def test_dry_run_prints_the_plan_and_runs_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            code = levels.main(["advanced", "--root", str(self.root), "--out", str(self.out), "--dry-run", "--base", "HEAD", "--threads", "4"])
        self.assertEqual(code, 0)
        self.assertIn("1. check-and-tests [database]: NEXTEST_TEST_THREADS=4 scripts/check.sh --tests", shown.getvalue())
        self.assertFalse(self.out.exists())

    def test_outside_a_checkout_and_bad_arguments_are_refused(self):
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(levels.main(["basic", "--root", self._tmp.name]), 2)
            self.assertEqual(levels.main(["basic", "--root", str(self.root), "--threads", "0"]), 2)
            self.assertEqual(levels.main(["basic", "--root", str(self.root), "--base=--upload-pack=x"]), 2)
        self.assertIn("scripts/check.sh was not found", said.getvalue())


if __name__ == "__main__":
    unittest.main()
