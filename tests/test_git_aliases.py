"""Base-branch detection behind the git base, git dm and git dmr aliases."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_reliability import ROOT

GIT = shutil.which("git")


@unittest.skipUnless(GIT, "git is required")
class GitBaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="chezmoi-regression-")
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        (home / ".local/libexec").mkdir(parents=True)
        shutil.copyfile(ROOT / "dot_local/libexec/git-base.sh", home / ".local/libexec/git-base.sh")
        self.repo = home / "repo"
        (self.repo / "sub").mkdir(parents=True)
        self.env = dict(
            os.environ, HOME=str(home), GIT_CONFIG_GLOBAL=str(ROOT / "dot_gitconfig"),
            GIT_CONFIG_NOSYSTEM="1", GIT_PAGER="cat",
            GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="commit.gpgsign", GIT_CONFIG_VALUE_0="false",
            GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
        )
        self.git("init", "--quiet", "-b", "main")
        self.commit("shared")

    def run_git(self, *args, cwd=None):
        return subprocess.run(
            [GIT, *args], cwd=cwd or self.repo, env=self.env,
            capture_output=True, text=True, timeout=15,
        )

    def git(self, *args, cwd=None):
        result = self.run_git(*args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, name):
        (self.repo / "sub" / name).write_text(name + "\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", name)

    def test_branch_from_develop_compares_with_develop_both_ways(self):
        self.git("switch", "--quiet", "-c", "develop")
        self.commit("develop-before")
        self.git("switch", "--quiet", "-c", "feature")
        self.commit("feature")
        self.git("switch", "--quiet", "develop")
        self.commit("develop-after")
        self.git("switch", "--quiet", "feature")
        self.assertEqual(self.git("base"), "develop")
        self.assertEqual(self.git("dm", "--name-only"), "sub/feature")
        self.assertEqual(self.git("dmr", "--name-only"), "sub/develop-after")
        # aliases run from the top level; relative paths must still match from a subdirectory
        self.assertEqual(self.git("dm", "--name-only", "--", "feature", cwd=self.repo / "sub"), "sub/feature")

    def test_stacked_branch_compares_with_its_unpushed_parent(self):
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("switch", "--quiet", "-c", "parent")
        self.commit("parent")
        self.git("update-ref", "refs/remotes/origin/parent", "HEAD")
        self.commit("parent-unpushed")
        self.git("switch", "--quiet", "-c", "child")
        self.commit("child")
        self.assertEqual(self.git("base"), "parent")

    def test_origin_copy_beats_stale_local_branch(self):
        self.git("switch", "--quiet", "-c", "other")
        self.commit("other")
        self.git("switch", "--quiet", "main")
        self.commit("upstream")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("reset", "--quiet", "--hard", "HEAD~")
        self.git("switch", "--quiet", "other")
        self.git("switch", "--quiet", "-c", "fix", "origin/main")
        self.assertEqual(self.git("base"), "origin/main")

    def test_own_remote_copy_is_never_the_base(self):
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.commit("topic")
        self.git("update-ref", "refs/remotes/origin/topic", "HEAD")
        self.git("reset", "--quiet", "--hard", "HEAD~")
        self.git("switch", "--quiet", "-c", "topic", "origin/topic")
        self.assertEqual(self.git("base"), "origin/main")

    def test_without_a_base_reports_failure_instead_of_diffing(self):
        for alias in ["base", "dm", "dmr"]:
            with self.subTest(alias=alias):
                result = self.run_git(alias)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("git base: no start point", result.stderr)


if __name__ == "__main__":
    unittest.main()
