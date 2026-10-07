"""Clipboard recovery checks using command stubs; no services are restarted."""

import os
import shlex
import unittest

from test_reliability import FishTest, ROOT

FUNCTION = ROOT / "private_dot_config/private_fish/functions/fix-clipboard.fish"


class ClipboardTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "clipboard-calls"
        self.env.update(
            TEST_CLIPBOARD_CALLS=str(self.calls), TEST_DEFAULTS_STATUS="0",
            TEST_SHARINGD_LOOKUP_STATUS="0", TEST_PBOARD_LOOKUP_STATUS="0",
            TEST_SHARINGD_KILL_STATUS="0", TEST_PBOARD_KILL_STATUS="0",
            TEST_SUDO_STATUS="0",
        )
        stub = self.bin / "clipboard-stub"
        stub.write_text("""#!/bin/sh
tool=${0##*/}
printf '%s\n' "$tool $*" >> "$TEST_CLIPBOARD_CALLS"
stub_status=0
case "$tool" in
    defaults) stub_status=$TEST_DEFAULTS_STATUS ;;
    pgrep)
        for service in "$@"; do :; done
        case "$service" in
            sharingd) stub_status=$TEST_SHARINGD_LOOKUP_STATUS ;;
            pboard) stub_status=$TEST_PBOARD_LOOKUP_STATUS ;;
        esac ;;
    killall)
        case "$1" in
            sharingd) stub_status=$TEST_SHARINGD_KILL_STATUS ;;
            pboard) stub_status=$TEST_PBOARD_KILL_STATUS ;;
        esac ;;
    sudo) stub_status=$TEST_SUDO_STATUS ;;
esac
if [ "$stub_status" != 0 ] && ! { [ "$tool" = pgrep ] && [ "$stub_status" = 1 ]; }; then
    printf 'stub: %s failed\n' "$tool" >&2
fi
exit "$stub_status"
""")
        stub.chmod(0o700)
        for name in ["defaults", "pgrep", "killall", "sudo"]:
            (self.bin / name).symlink_to(stub)

    def recover(self):
        return self.run_fish(f"source {shlex.quote(str(FUNCTION))}\nfix-clipboard")

    def test_success_includes_bluetooth_without_claiming_clipboard_is_fixed(self):
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [
            "defaults write com.apple.sharingd DisallowHandoff -bool false",
            f"pgrep -U {os.getuid()} -x sharingd", "killall sharingd",
            f"pgrep -U {os.getuid()} -x pboard", "killall pboard",
            "sudo killall bluetoothd",
        ])
        self.assertIn("Restart signals sent", result.stdout)
        self.assertIn("Try copying between your devices", result.stdout)
        self.assertNotIn("reset completed", result.stdout)

    def test_command_errors_are_visible_and_stop_recovery(self):
        for variable, code, last_command in [
            ("TEST_DEFAULTS_STATUS", 9, "defaults write com.apple.sharingd DisallowHandoff -bool false"),
            ("TEST_SHARINGD_KILL_STATUS", 7, "killall sharingd"),
            ("TEST_PBOARD_KILL_STATUS", 6, "killall pboard"),
            ("TEST_SUDO_STATUS", 5, "sudo killall bluetoothd"),
        ]:
            with self.subTest(variable=variable):
                self.env[variable] = str(code)
                result = self.recover()
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn("failed", result.stderr)
                if last_command.startswith("killall "):
                    self.assertIn(f"could not restart {last_command.split()[1]}", result.stderr)
                self.assertEqual(self.calls.read_text().splitlines()[-1], last_command)
                self.assertNotIn("Restart signals sent", result.stdout)
                self.env[variable] = "0"
                self.calls.unlink()

    def test_missing_user_services_still_restart_bluetooth(self):
        self.env.update(TEST_SHARINGD_LOOKUP_STATUS="1", TEST_PBOARD_LOOKUP_STATUS="1")
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("sharingd is not running; skipping", result.stdout)
        self.assertIn("pboard is not running; skipping", result.stdout)
        self.assertEqual(self.calls.read_text().splitlines(), [
            "defaults write com.apple.sharingd DisallowHandoff -bool false",
            f"pgrep -U {os.getuid()} -x sharingd",
            f"pgrep -U {os.getuid()} -x pboard",
            "sudo killall bluetoothd",
        ])

    def test_lookup_errors_do_not_kill_processes(self):
        for service in ["sharingd", "pboard"]:
            with self.subTest(service=service):
                variable = f"TEST_{service.upper()}_LOOKUP_STATUS"
                self.env[variable] = "3"
                result = self.recover()
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn(f"could not check {service}", result.stderr)
                self.assertNotIn(f"killall {service}", self.calls.read_text())
                self.assertNotIn("sudo", self.calls.read_text())
                self.assertNotIn("Restart signals sent", result.stdout)
                self.env[variable] = "0"
                self.calls.unlink()


if __name__ == "__main__":
    unittest.main()
