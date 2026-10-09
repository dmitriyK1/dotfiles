"""Offline checks: python3 -B -m unittest discover -s tests -v.

Each fish process uses a temporary HOME and mocked update commands, including
the two absolute executable paths in the update script.
"""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FISH = shutil.which("fish")


@unittest.skipUnless(FISH, "fish is required")
class FishTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chezmoi-regression-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        fish_wrapper = self.bin / "fish"
        fish_wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(FISH)} "$@"\n')
        fish_wrapper.chmod(0o700)
        self.env = dict(os.environ)
        self.env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            XDG_CACHE_HOME=str(self.home / ".cache"),
            XDG_DATA_HOME=str(self.home / ".local/share"),
            XDG_STATE_HOME=str(self.home / ".local/state"),
            PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        )

    def run_fish(self, code):
        return subprocess.run(
            [FISH, "--no-config", "-c", code], env=self.env,
            text=True, capture_output=True, timeout=15,
        )


class UpdateTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "calls"
        self.env.update(
            TEST_CALLS=str(self.calls), TEST_FAIL_COMMAND="",
            TEST_NPM_STATUS="0", TEST_NPM_OUTPUT="", TEST_CUT_STATUS="0",
        )
        self.stub = self.bin / "stub"
        self.stub.write_text("""#!/bin/sh
tool=$1
shift
printf '%s\n' "$tool $*" >> "$TEST_CALLS"
if [ "$tool $*" = "$TEST_FAIL_COMMAND" ]; then exit 9; fi
if [ "$tool" = npm ] && [ "$1" = outdated ]; then
    printf '%s' "$TEST_NPM_OUTPUT"
    exit "$TEST_NPM_STATUS"
fi
if [ "$tool" = cut ]; then
    if [ "$TEST_CUT_STATUS" != 0 ]; then exit "$TEST_CUT_STATUS"; fi
    exec /usr/bin/cut "$@"
fi
exit 0
""")
        self.stub.chmod(0o700)

    def run_update(self, optional=False):
        names = [
            "brew", "chezmoi", "atuin", "nvim", "fisher",
            "fish_update_completions", "omf", "cut",
        ]
        if optional:
            names += ["uv", "rustup"]
        prelude = "".join(
            f"function {name}; command {shlex.quote(str(self.stub))} {name} $argv; end\n"
            for name in names
        )
        for function, tool in [
            ("__test_npm", "npm"), ("__test_softwareupdate", "softwareupdate"),
        ]:
            prelude += (
                f"function {function}; command {shlex.quote(str(self.stub))} "
                f"{tool} $argv; end\n"
            )
        script = (ROOT / "dot_local/bin/executable_update.fish").read_text()
        script = script.replace("/opt/homebrew/bin/npm", "__test_npm")
        script = script.replace("/usr/sbin/softwareupdate", "__test_softwareupdate")
        return self.run_fish(prelude + script)

    def set_outdated(self):
        self.env["TEST_NPM_STATUS"] = "1"
        self.env["TEST_NPM_OUTPUT"] = (
            "/prefix/pkg:pkg@2.0.0:pkg@1.0.0:pkg@2.0.0:global\n"
            "/prefix/@scope/pkg:@scope/pkg@3.0.0:@scope/pkg@2.0.0:"
            "@scope/pkg@3.0.0:global\n"
        )

    def test_success_and_optional_skips(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = result.stdout.split(">>> update summary", 1)[1]
        self.assertEqual(summary.count(": OK"), 12)
        self.assertIn("uv: SKIPPED (not installed)", summary)
        self.assertIn("rustup: SKIPPED (not installed)", summary)
        self.assertIn("all global npm packages are up to date", result.stdout)
        self.assertNotIn("npm install", self.calls.read_text())

    def test_each_step_failure_is_reported_and_later_steps_run(self):
        steps = {
            "brew update": "brew update",
            "brew upgrade --greedy-auto-updates --yes": "brew upgrade",
            "brew cleanup": "brew cleanup",
            "brew tap --repair": "brew tap --repair",
            "chezmoi update": "chezmoi update",
            "atuin sync": "atuin sync",
            "nvim --headless +Lazy! sync +UpdateRemotePlugins +qa": "neovim plugins",
            "fisher update": "fisher update",
            "fish_update_completions ": "fish completions",
            "omf update": "omf update",
            "softwareupdate --all --install --force": "Apple updates",
        }
        for command, label in steps.items():
            with self.subTest(command=command):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_FAIL_COMMAND"] = command
                result = self.run_update()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"{label}: FAILED (exit 9)", result.stdout)
                self.assertIn("softwareupdate --all --install --force", self.calls.read_text())

    def test_outdated_packages_are_installed_with_scoped_names(self):
        self.set_outdated()
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("npm install -g pkg@2.0.0 @scope/pkg@3.0.0", self.calls.read_text())
        self.assertIn("global npm packages: OK", result.stdout)
        self.assertNotIn("all global npm packages are up to date", result.stdout)

    def test_npm_failure_is_not_reported_as_up_to_date(self):
        for status in ["1", "2", "127"]:
            with self.subTest(status=status):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_NPM_STATUS"] = status
                result = self.run_update()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"global npm packages: FAILED (exit {status})", result.stdout)
                self.assertNotIn("all global npm packages are up to date", result.stdout)
                self.assertNotIn("npm install", self.calls.read_text())
                self.assertIn("Apple updates: OK", result.stdout)

    def test_cut_failure_is_reported(self):
        self.set_outdated()
        self.env["TEST_CUT_STATUS"] = "3"
        result = self.run_update()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("global npm packages: FAILED (exit 3)", result.stdout)
        self.assertNotIn("npm install", self.calls.read_text())

    def test_npm_install_failure_is_reported(self):
        self.set_outdated()
        self.env["TEST_FAIL_COMMAND"] = "npm install -g pkg@2.0.0 @scope/pkg@3.0.0"
        result = self.run_update()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("global npm packages: FAILED (exit 9)", result.stdout)
        self.assertIn("Apple updates: OK", result.stdout)

    def test_optional_tools_success_and_failures(self):
        result = self.run_update(optional=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for label in ["uv self update", "uv tool upgrade", "rustup update"]:
            self.assertIn(f"{label}: OK", result.stdout)
        for command, label in [
            ("uv self update", "uv self update"),
            ("uv tool upgrade --all", "uv tool upgrade"),
            ("rustup update", "rustup update"),
        ]:
            with self.subTest(command=command):
                self.env["TEST_FAIL_COMMAND"] = command
                result = self.run_update(optional=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"{label}: FAILED (exit 9)", result.stdout)
                self.assertIn("Apple updates: OK", result.stdout)


class AliasCacheTests(FishTest):
    def setUp(self):
        super().setUp()
        self.alias_dir = self.home / ".config/fish"
        self.alias_dir.mkdir(parents=True)
        self.main = self.alias_dir / ".fish_aliases"
        self.local = self.alias_dir / ".fish_aliases.local"
        self.cache = self.home / ".cache/fish/aliases.fish"
        self.main.write_text("""abbr -a shared base-command
alias basealias 'printf base-alias'
if test -f ~/.config/fish/.fish_aliases.local
    source ~/.config/fish/.fish_aliases.local
end
""")
        # Exercise production code without starting unrelated integrations.
        config = (ROOT / "private_dot_config/private_fish/config.fish").read_text()
        self.block = config[
            config.index("    # defining aliases"):
            config.index("    [ -f $HOME/.config/fish/config.local.fish ]")
        ]
        self.inspect = """
printf '\nBASE_ALIAS='
basealias
printf '\nSHARED_ABBR='
abbr --query shared
printf '%s\n' $status
printf 'LOCAL_ABBR='
abbr --query localabbr
printf '%s\n' $status
if functions -q shared
    printf 'SHARED_FUNCTION='
    shared
    echo
end
"""

    def load(self):
        result = self.run_fish(self.block + self.inspect)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def write_local(self):
        self.local.write_text("alias shared 'printf local-alias'\nabbr -a localabbr local-command\n")

    def test_first_load_and_cache_reuse(self):
        result = self.load()
        self.assertEqual(result.stderr, "")
        self.assertIn("BASE_ALIAS=base-alias", result.stdout)
        self.assertIn("SHARED_ABBR=0", result.stdout)
        self.assertTrue(self.cache.read_text().startswith("# aliases-v1 local=missing\n"))
        before = (self.cache.read_bytes(), self.cache.stat().st_mtime_ns)
        self.load()
        self.assertEqual(before, (self.cache.read_bytes(), self.cache.stat().st_mtime_ns))

    def test_local_creation_and_alias_over_abbreviation(self):
        self.load()
        self.write_local()
        # Presence must invalidate the cache even with an old local timestamp.
        older = self.cache.stat().st_mtime_ns - 2_000_000_000
        os.utime(self.local, ns=(older, older))
        result = self.load()
        self.assertEqual(result.stderr, "")
        self.assertIn("SHARED_ABBR=1", result.stdout)
        self.assertIn("SHARED_FUNCTION=local-alias", result.stdout)
        self.assertIn("LOCAL_ABBR=0", result.stdout)
        self.assertTrue(self.cache.read_text().startswith("# aliases-v1 local=present\n"))

    def test_local_deletion_removes_cached_overrides(self):
        self.write_local()
        self.load()
        self.local.unlink()
        result = self.load()
        self.assertEqual(result.stderr, "")
        self.assertIn("SHARED_ABBR=0", result.stdout)
        self.assertIn("LOCAL_ABBR=1", result.stdout)
        self.assertNotIn("SHARED_FUNCTION=", result.stdout)
        self.assertNotIn("local-alias", self.cache.read_text())

    def test_changes_to_either_file_rebuild_cache(self):
        self.write_local()
        self.load()
        for file, old, new, expected in [
            (self.main, "base-alias", "new-base", "BASE_ALIAS=new-base"),
            (self.local, "local-alias", "new-local", "SHARED_FUNCTION=new-local"),
        ]:
            with self.subTest(file=file.name):
                newer = self.cache.stat().st_mtime_ns + 2_000_000_000
                file.write_text(file.read_text().replace(old, new))
                os.utime(file, ns=(newer, newer))
                self.assertIn(expected, self.load().stdout)

    def test_old_cache_without_header_is_migrated(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("abbr -a stale old-command\n")
        result = self.load()
        self.assertEqual(result.stderr, "")
        self.assertNotIn("stale", self.cache.read_text())
        self.assertTrue(self.cache.read_text().startswith("# aliases-v1 local=missing\n"))

    def test_generation_failure_keeps_old_file_and_loads_source(self):
        self.load()
        previous = self.cache.read_bytes()
        newer = self.cache.stat().st_mtime_ns + 2_000_000_000
        self.main.write_text("alias basealias 'printf fallback-alias'\nreturn 7\n")
        os.utime(self.main, ns=(newer, newer))
        result = self.load()
        self.assertIn("could not rebuild aliases cache", result.stderr)
        self.assertIn("BASE_ALIAS=fallback-alias", result.stdout)
        self.assertEqual(self.cache.read_bytes(), previous)
        self.assertEqual(list(self.cache.parent.glob("aliases.fish.*")), [])

    def test_concurrent_shells_publish_complete_cache(self):
        # Force both generators to overlap rather than relying on scheduling.
        started = self.home / "generators"
        self.env.update(TEST_GENERATORS=str(started), TEST_REAL_FISH=FISH)
        wrapper = self.bin / "fish"
        wrapper.write_text("""#!/bin/sh
printf 'started\n' >> "$TEST_GENERATORS"
attempt=0
while [ "$(wc -l < "$TEST_GENERATORS")" -lt 2 ]; do
    attempt=$((attempt + 1))
    if [ "$attempt" -gt 200 ]; then exit 8; fi
    sleep 0.01
done
exec "$TEST_REAL_FISH" "$@"
""")
        wrapper.chmod(0o700)
        processes = []
        try:
            for _ in range(2):
                processes.append(subprocess.Popen(
                    [FISH, "--no-config", "-c", self.block + self.inspect],
                    env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                ))
            for process in processes:
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assertIn("BASE_ALIAS=base-alias", stdout)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        self.assertEqual(list(self.cache.parent.glob("aliases.fish.*")), [])
        checked = subprocess.run(
            [FISH, "--no-config", "--no-execute", str(self.cache)],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
