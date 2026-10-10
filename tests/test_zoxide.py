"""Shared zoxide fuzzy fallback checks against a temporary native database."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_reliability import FISH, ROOT

HELPER = ROOT / "dot_local/libexec/zoxide-fuzzy.py"
NATIVE = Path("/opt/homebrew/bin/zoxide")
spec = importlib.util.spec_from_file_location("zoxide_fuzzy", HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@unittest.skipUnless(NATIVE.is_file(), "Homebrew zoxide is required")
class ZoxideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chezmoi-zoxide-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        libexec = self.home / ".local/libexec"
        libexec.mkdir()
        shutil.copyfile(HELPER, libexec / "zoxide-fuzzy.py")
        wrapper = self.bin / "zoxide"
        shutil.copyfile(ROOT / "dot_local/bin/executable_zoxide", wrapper)
        wrapper.chmod(0o700)
        self.env = dict(os.environ, HOME=str(self.home),
                        _ZO_DATA_DIR=str(self.home / "zoxide-data"),
                        _ZO_EXCLUDE_DIRS="", PYTHONDONTWRITEBYTECODE="1",
                        PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin")
        self.target = self.home / "projects with spaces & 'quote'" / "ext-platform360"
        self.add_directory(self.target)

    def add_directory(self, path, visits=1):
        path.mkdir(parents=True, exist_ok=True)
        for _ in range(visits):
            subprocess.run([str(NATIVE), "add", "--", str(path)], env=self.env,
                           capture_output=True, check=True, timeout=5)

    def query(self, *arguments, native=False):
        binary = NATIVE if native else self.bin / "zoxide"
        return subprocess.run([str(binary), "query", *arguments], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_shortcuts_and_typo_find_directory(self):
        for keyword in ("ext360", "EXT360", "e360", "ext-360", "platform-360", "ext-platfrom360"):
            with self.subTest(keyword=keyword):
                self.assertNotEqual(self.query(keyword, native=True).returncode, 0)
                result = self.query(keyword)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"{self.target}\n")
                self.assertEqual(result.stderr, "")

    def test_native_match_wins_over_more_frequent_fuzzy_match(self):
        exact = self.home / "ext-360"
        self.add_directory(exact)
        self.add_directory(self.target, visits=5)
        result = self.query("ext-360")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{exact}\n")

    def test_superfile_scored_list_preserves_format_and_frecency_order(self):
        other = self.home / "other" / "ext-platform360"
        self.add_directory(other, visits=4)
        expected = self.query("--list", "--score", native=True)
        for keyword in ("ext360", "ext-360", "platform-360"):
            with self.subTest(keyword=keyword):
                result = self.query("-ls", keyword)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected.stdout)
                self.assertEqual(result.stdout.splitlines()[0].split(maxsplit=1)[1], str(other))

    def test_exclude_applies_to_fuzzy_matches(self):
        result = self.query("--exclude", str(self.target), "--", "ext-360")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "zoxide: no match found\n")
        self.assertEqual(self.query("--list", "--exclude", str(self.target),
                                    "ext-360").stdout, "")

    def test_base_directory_applies_to_fuzzy_matches(self):
        outside = self.home / "outside" / "ext-platform360"
        self.add_directory(outside, visits=5)
        result = self.query("--base-dir", str(self.target.parent), "ext-360")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{self.target}\n")

    def test_earlier_keywords_still_restrict_paths(self):
        outside = self.home / "outside" / "ext-platform360"
        self.add_directory(outside, visits=5)
        for keyword in ("ext360", "ext-360"):
            with self.subTest(keyword=keyword):
                result = self.query("projects", keyword)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"{self.target}\n")

    def test_unrelated_or_reordered_query_retains_no_match_and_status(self):
        for keyword in ("completely-unrelated", "360ext"):
            with self.subTest(keyword=keyword):
                result = self.query(keyword)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "zoxide: no match found\n")

    def test_empty_and_exact_lists_remain_native(self):
        for arguments in (("-ls",), ("--list", "platform360"),
                          ("--list", "completely-unrelated")):
            with self.subTest(arguments=arguments):
                result = self.query(*arguments)
                native = self.query(*arguments, native=True)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (native.returncode, native.stdout, native.stderr))

    def test_help_unknown_options_and_path_queries_remain_native(self):
        for arguments in (("--help",), ("--unknown",), ("--exclude",),
                          ("projects/ext-360",)):
            with self.subTest(arguments=arguments):
                result = self.query(*arguments)
                native = self.query(*arguments, native=True)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (native.returncode, native.stdout, native.stderr))

    def test_non_query_commands_remain_native(self):
        for arguments in (("--version",), ("init", "fish", "--cmd", "j")):
            with self.subTest(arguments=arguments):
                result = subprocess.run([str(self.bin / "zoxide"), *arguments],
                                        env=self.env, capture_output=True, timeout=5)
                native = subprocess.run([str(NATIVE), *arguments], env=self.env,
                                        capture_output=True, timeout=5)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (native.returncode, native.stdout, native.stderr))

    @unittest.skipUnless(FISH, "fish is required")
    def test_fish_j_uses_shared_fallback(self):
        for keyword in ("ext360", "ext-360", "platform-360"):
            with self.subTest(keyword=keyword):
                result = subprocess.run([FISH, "--no-config", "-c", """
zoxide init fish --cmd j | source
j $argv[1]
set -l result $status
pwd
exit $result
""", keyword], cwd=self.home, env=self.env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(self.target))


class ZoxideFailureTests(unittest.TestCase):
    def test_database_errors_do_not_trigger_fuzzy_search(self):
        failure = subprocess.CompletedProcess([], 1, b"", b"zoxide: database unavailable\n")
        with patch.object(module.subprocess, "run", return_value=failure) as run:
            with patch.object(module, "write_result", return_value=1) as write:
                self.assertEqual(module.main(["query", "ext-360"]), 1)
                run.assert_called_once()
                write.assert_called_once_with(failure)

    def test_fallback_listing_errors_remain_visible(self):
        missing = subprocess.CompletedProcess([], 1, b"", b"zoxide: no match found\n")
        failure = subprocess.CompletedProcess([], 9, b"", b"zoxide: failed to read database\n")
        with patch.object(module.subprocess, "run", side_effect=(missing, failure)):
            with patch.object(module, "write_result", return_value=9) as write:
                self.assertEqual(module.main(["query", "ext-360"]), 9)
                write.assert_called_once_with(failure)

    def test_interactive_queries_delegate_with_terminal_intact(self):
        with patch.object(module.os, "execv", side_effect=RuntimeError("delegated")) as execute:
            with self.assertRaisesRegex(RuntimeError, "delegated"):
                module.main(["query", "--interactive", "ext-360"])
            execute.assert_called_once_with(module.ZOXIDE,
                                            [module.ZOXIDE, "query", "--interactive", "ext-360"])
