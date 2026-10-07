"""LazyVim bootstrap and gro checks, with no network or package installation."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from test_reliability import FishTest, ROOT

GIT = shutil.which("git")


@unittest.skipUnless(GIT, "git is required")
class LazyVimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chezmoi-lazyvim-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.target = self.home / ".config/nvim"
        self.calls = self.root / "clones"
        self.env = dict(os.environ)
        self.env.update(
            HOME=str(self.home), TMPDIR=str(self.tmp),
            PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
            TEST_REAL_GIT=GIT, TEST_CLONES=str(self.calls), TEST_FAIL_CLONE="0",
        )
        self.starter = self.root / "starter"
        self.starter.mkdir()
        for name, content in {
            "init.lua": 'require("config.lazy")\n',
            "lua/config/lazy.lua": "-- starter bootstrap\n",
            "lua/config/options.lua": "-- starter options\n",
            ".gitignore": "lazy-lock.json\n",
        }.items():
            file = self.starter / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        for args in [
            ["init", "--quiet", str(self.starter)],
            ["-C", str(self.starter), "add", "."],
            ["-C", str(self.starter), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture"],
        ]:
            subprocess.run([GIT, *args], env=self.env, check=True, capture_output=True, timeout=15)
        self.env["TEST_STARTER"] = str(self.starter)
        wrapper = self.bin / "git"
        wrapper.write_text("""#!/bin/sh
if [ "$1" = clone ]; then
    printf 'clone\n' >> "$TEST_CLONES"
    if [ "$TEST_FAIL_CLONE" = 1 ]; then exit 6; fi
    exec "$TEST_REAL_GIT" clone --depth=1 "$TEST_STARTER" "$4"
fi
exec "$TEST_REAL_GIT" "$@"
""")
        wrapper.chmod(0o700)

    def install(self):
        return subprocess.run(
            ["/bin/bash", str(ROOT / "run_onchange_before_15-install-lazyvim.sh")],
            env=self.env, capture_output=True, text=True, timeout=15,
        )

    def test_fresh_install_and_repeat(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "init.lua").read_text(), 'require("config.lazy")\n')
        self.assertTrue((self.target / "lua/config/lazy.lua").is_file())
        self.assertTrue((self.target / ".gitignore").is_file())
        self.assertFalse((self.target / ".git").exists())
        self.assertEqual(list(self.tmp.iterdir()), [])
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), "clone\n")

    def test_existing_entrypoints_are_preserved(self):
        self.target.mkdir(parents=True)
        for name, symlink in [("init.lua", False), ("init.vim", False), ("init.lua", True)]:
            with self.subTest(name=name, symlink=symlink):
                entry = self.target / name
                if symlink:
                    entry.symlink_to(self.target / "missing.lua")
                else:
                    entry.write_text("existing config\n")
                result = self.install()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(self.calls.exists())
                if symlink:
                    self.assertTrue(entry.is_symlink())
                else:
                    self.assertEqual(entry.read_text(), "existing config\n")
                entry.unlink()

    def test_partial_setup_preserves_customizations(self):
        options = self.target / "lua/config/options.lua"
        options.parent.mkdir(parents=True)
        options.write_text("-- my options\n")
        custom = self.target / "lua/plugins/custom.lua"
        custom.parent.mkdir(parents=True)
        custom.write_text("-- my plugin\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(options.read_text(), "-- my options\n")
        self.assertEqual(custom.read_text(), "-- my plugin\n")
        self.assertTrue((self.target / "init.lua").is_file())
        self.assertTrue((self.target / "lua/config/lazy.lua").is_file())

    def test_clone_failure_leaves_config_untouched(self):
        self.env["TEST_FAIL_CLONE"] = "1"
        result = self.install()
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_copy_failure_can_be_retried_without_publishing_entrypoint(self):
        wrapper = self.bin / "cp"
        wrapper.write_text("""#!/bin/sh
case "$2" in
    */lua/config/lazy.lua)
        printf 'partial' > "$3"
        exit 8 ;;
esac
exec /bin/cp "$@"
""")
        wrapper.chmod(0o700)
        result = self.install()
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertFalse((self.target / "init.lua").exists())
        self.assertFalse((self.target / "lua/config/lazy.lua").exists())
        self.assertEqual(list(self.target.rglob("*.??????")), [])
        self.assertEqual(list(self.tmp.iterdir()), [])
        wrapper.unlink()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / "lua/config/lazy.lua").is_file())
        self.assertEqual((self.target / "init.lua").read_text(), 'require("config.lazy")\n')

    def test_partial_entrypoint_copy_is_cleaned_up_and_retry_succeeds(self):
        wrapper = self.bin / "cp"
        wrapper.write_text("""#!/bin/sh
case "$2" in
    */init.lua)
        printf 'partial' > "$3"
        exit 8 ;;
esac
exec /bin/cp "$@"
""")
        wrapper.chmod(0o700)
        result = self.install()
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertFalse((self.target / "init.lua").exists())
        self.assertEqual(list(self.target.glob("init.lua.*")), [])
        wrapper.unlink()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "init.lua").read_text(), 'require("config.lazy")\n')


class GroTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "gron-calls"
        self.env.update(
            TEST_GRON_CALLS=str(self.calls), TEST_GRON_STATUS="0", TEST_UNGRON_STATUS="0",
        )
        stub = self.bin / "gron"
        stub.write_text("""#!/bin/sh
printf '%s\n' "$*" >> "$TEST_GRON_CALLS"
if [ "$1" = --ungron ]; then
    cat
    exit "$TEST_UNGRON_STATUS"
fi
printf 'json["-foo"] = "value";\njson.other = "untouched";\n'
exit "$TEST_GRON_STATUS"
""")
        stub.chmod(0o700)

    def gro(self, *args):
        source = ROOT / "private_dot_config/private_fish/dot_fish_functions"
        return self.run_fish(f"source {shlex.quote(str(source))}\ngro {shlex.join(args)}")

    def test_literal_filter_starting_with_dash_and_spaced_filename(self):
        result = self.gro("-foo", "file with spaces.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('json["-foo"]', result.stdout)
        self.assertNotIn("untouched", result.stdout)
        self.assertCountEqual(self.calls.read_text().splitlines(), ["-- file with spaces.json", "--ungron"])

    def test_wrong_argument_count(self):
        for args in [(), ("filter",), ("filter", "file", "extra")]:
            with self.subTest(args=args):
                result = self.gro(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("usage: gro", result.stderr)
                self.assertFalse(self.calls.exists())

    def test_no_matches(self):
        result = self.gro("absent", "file.json")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_gron_errors_propagate(self):
        for variable, status in [("TEST_GRON_STATUS", "3"), ("TEST_UNGRON_STATUS", "5")]:
            with self.subTest(variable=variable):
                self.env[variable] = status
                result = self.gro("-foo", "file.json")
                self.assertEqual(result.returncode, int(status), result.stderr)
                self.env[variable] = "0"


if __name__ == "__main__":
    unittest.main()
