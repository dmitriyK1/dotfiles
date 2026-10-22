"""Offline package installation and optional-tool template checks."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHEZMOI = shutil.which("chezmoi")
INSTALLER = "run_onchange_before_10-install-packages.sh.tmpl"


@unittest.skipUnless(CHEZMOI, "chezmoi is required")
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chezmoi-packages-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with spaces"
        self.source = self.root / "source with spaces"
        self.bin = self.root / "bin"
        for directory in (self.home, self.source, self.bin):
            directory.mkdir()
        self.local = self.home / ".config/homebrew/Brewfile.local"
        self.local.parent.mkdir(parents=True)
        (self.source / "Brewfile").write_text('brew "shared"\n')
        shutil.copytree(ROOT / ".chezmoitemplates", self.source / ".chezmoitemplates")
        self.config = self.root / "config.toml"
        self.config.write_text("")
        self.calls = self.root / "calls"
        self.env = dict(os.environ)
        self.env.update(
            HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
            XDG_CACHE_HOME=str(self.root / "cache"),
            PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            TEST_CALLS=str(self.calls), TEST_FAIL_BREWFILE="",
        )
        brew = self.bin / "brew"
        brew.write_text('''#!/bin/sh
if [ "$1" = shellenv ]; then exit 0; fi
[ "$1" = bundle ] && [ "$#" = 2 ] || exit 7
file=${2#--file=}
[ -f "$file" ] || exit 8
printf '%s\n' "$file" >> "$TEST_CALLS"
if [ "$file" = "$TEST_FAIL_BREWFILE" ]; then exit 9; fi
''')
        brew.chmod(0o700)

    def render(self, path=INSTALLER):
        result = subprocess.run(
            [CHEZMOI, "--config", str(self.config), "--source", str(self.source),
             "--destination", str(self.home), "--cache", str(self.root / "cache"),
             "--persistent-state", str(self.root / "state"), "execute-template"],
            input=(ROOT / path).read_text(), env=self.env,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def install(self):
        script = self.render().replace("/opt/homebrew/bin/brew", str(self.bin / "brew"))
        syntax = subprocess.run(["/bin/bash", "-n"], input=script, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        return subprocess.run(["/bin/bash"], input=script, env=self.env,
                              capture_output=True, text=True, timeout=15)

    def test_local_brewfile_is_optional(self):
        self.assertTrue(self.render().startswith("#!/bin/bash\n"))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [str(self.source / "Brewfile")])

    def test_shared_then_local_brewfile_with_spaces(self):
        self.local.write_text('brew "rtk"\n')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(),
                         [str(self.source / "Brewfile"), str(self.local)])

    def test_brewfile_changes_update_rendered_installer(self):
        absent = self.render()
        self.local.write_text('brew "rtk"\n')
        created = self.render()
        self.assertNotEqual(absent, created)
        self.local.write_text('brew "icm"\n')
        self.assertNotEqual(created, self.render())
        self.local.unlink()
        self.assertEqual(absent, self.render())
        (self.source / "Brewfile").write_text('brew "another-shared-tool"\n')
        self.assertNotEqual(absent, self.render())

    def test_installation_failures_propagate(self):
        self.local.write_text('brew "rtk"\n')
        for failing in (self.source / "Brewfile", self.local):
            with self.subTest(failing=failing):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_FAIL_BREWFILE"] = str(failing)
                result = self.install()
                self.assertEqual(result.returncode, 9, result.stderr)
                expected = [str(self.source / "Brewfile")]
                if failing == self.local:
                    expected.append(str(self.local))
                self.assertEqual(self.calls.read_text().splitlines(), expected)

    def test_local_installer_runs_after_packages_and_propagates_failures(self):
        self.local.write_text('brew "rtk"\n')
        installer = self.local.with_name("install.local.sh")
        for status in (0, 9):
            with self.subTest(status=status):
                self.calls.unlink(missing_ok=True)
                installer.write_text(f'printf "native tools\\n" >> "$TEST_CALLS"\nexit {status}\n')
                result = self.install()
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(self.calls.read_text().splitlines(),
                                 [str(self.source / "Brewfile"), str(self.local), "native tools"])

    def test_local_installer_changes_update_rendered_installer(self):
        absent = self.render()
        installer = self.local.with_name("install.local.sh")
        installer.write_text("echo first\n")
        created = self.render()
        self.assertNotEqual(absent, created)
        installer.write_text("echo second\n")
        self.assertNotEqual(created, self.render())
        installer.unlink()
        self.assertEqual(absent, self.render())

    def test_optional_instructions_follow_installed_tools(self):
        for tools in ((), ("rtk",), ("icm",), ("rtk", "icm")):
            with self.subTest(tools=tools):
                for tool in ("rtk", "icm"):
                    executable = self.bin / tool
                    executable.unlink(missing_ok=True)
                    if tool in tools:
                        executable.write_text("#!/bin/sh\nexit 0\n")
                        executable.chmod(0o700)
                rendered = self.render("private_dot_codex/AGENTS.md.tmpl")
                self.assertEqual("## Command output (RTK)" in rendered, "rtk" in tools)
                self.assertEqual("<!-- icm:start -->" in rendered, "icm" in tools)
                self.assertEqual("/.codex/RTK.md" in rendered, "rtk" in tools)
                claude = self.render("private_dot_claude/CLAUDE.md.tmpl")
                self.assertEqual("\n@RTK.md\n" in claude, "rtk" in tools)
                self.assertEqual("<!-- icm:start -->" in claude, "icm" in tools)
                self.assertFalse(claude.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
