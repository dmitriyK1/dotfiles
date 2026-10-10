"""Superfile shell integration checks using a temporary home and stub executable."""

import shlex

from test_reliability import FishTest, ROOT


class SuperfileTests(FishTest):
    def setUp(self):
        super().setUp()
        self.lastdir = self.home / "custom state/superfile/lastdir"
        self.lastdir.parent.mkdir(parents=True)
        self.target = self.home / "folder with spaces & $cash 'quote'"
        self.target.mkdir()
        self.content = self.home / "lastdir-content"
        self.content.write_text(f"cd -- {shlex.quote(str(self.target))}\n")
        self.args = self.home / "args"
        self.env.update(
            TEST_LASTDIR=str(self.lastdir), TEST_LASTDIR_CONTENT=str(self.content),
            TEST_SPF_ARGS=str(self.args), TEST_SPF_STATUS="0", TEST_WRITE_LASTDIR="1",
            TEST_PATH_STATUS="0",
        )
        stub = self.bin / "spf"
        stub.write_text("""#!/bin/sh
if [ "$1" = pl ] && [ "$2" = --lastdir-file ]; then
    [ "$TEST_PATH_STATUS" = 0 ] || exit "$TEST_PATH_STATUS"
    printf '%s\n' "$TEST_LASTDIR"
    exit 0
fi
printf '%s\n' "$@" > "$TEST_SPF_ARGS"
if [ "$TEST_WRITE_LASTDIR" = 1 ]; then
    cp "$TEST_LASTDIR_CONTENT" "$TEST_LASTDIR"
fi
exit "$TEST_SPF_STATUS"
""")
        stub.chmod(0o700)

    def call(self, *args):
        function = ROOT / "private_dot_config/private_fish/functions/spf.fish"
        return self.run_fish(f"""source {shlex.quote(str(function))}
cd -- "$HOME"
spf {shlex.join(args)}
set -l result $status
pwd
exit $result
""")

    def test_quit_changes_directory_and_preserves_arguments(self):
        result = self.call("--config-file", "config with spaces.toml", "--", str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.target))
        self.assertEqual(self.args.read_text().splitlines(), [
            "--config-file", "config with spaces.toml", "--", str(self.target),
        ])
        self.assertFalse(self.lastdir.exists())

    def test_help_without_lastdir_keeps_directory_and_discards_stale_state(self):
        self.lastdir.write_text(self.content.read_text())
        self.env["TEST_WRITE_LASTDIR"] = "0"
        result = self.call("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.home))
        self.assertFalse(self.lastdir.exists())

    def test_failed_launch_keeps_directory_and_exit_status(self):
        self.env["TEST_SPF_STATUS"] = "7"
        result = self.call()
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.home))
        self.assertFalse(self.lastdir.exists())

    def test_removed_directory_reports_cd_failure_and_cleans_state(self):
        self.target.rmdir()
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), str(self.home))
        self.assertFalse(self.lastdir.exists())

    def test_path_lookup_failure_does_not_launch_or_consume_state(self):
        self.lastdir.write_text(self.content.read_text())
        self.env["TEST_PATH_STATUS"] = "9"
        result = self.call()
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.home))
        self.assertFalse(self.args.exists())
        self.assertTrue(self.lastdir.exists())
