"""Fish prompt bootstrap checks, with no downloads or live home changes."""

import subprocess

from test_reliability import FishTest, ROOT


class FishPromptInstallTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "prompt-calls"
        self.env.update(
            TEST_CALLS=str(self.calls), TEST_INSTALL_STATUS="0",
            TEST_CONFIGURE_STATUS="0", TEST_PLUGIN_PRESENT="1",
        )
        functions = self.home / ".config/fish/functions"
        functions.mkdir(parents=True)
        (functions / "fisher.fish").write_text("""function fisher
    echo fisher >>$TEST_CALLS
    test $TEST_INSTALL_STATUS -eq 0; or exit $TEST_INSTALL_STATUS
    if test $TEST_PLUGIN_PRESENT = 1
        set -U _fisher_plugins ilancosman/tide@v6
    end
    # Tide's fish_prompt exits the installer process when sourced.
    exit 0
end
""")
        (functions / "tide.fish").write_text("""function tide
    echo tide >>$TEST_CALLS
    return $TEST_CONFIGURE_STATUS
end
""")
        self.omf = self.home / ".local/share/omf"
        self.omf.mkdir(parents=True)
        self.loader = self.home / ".config/fish/conf.d/omf.fish"
        self.loader.parent.mkdir()
        self.loader.write_text("# Old theme loader\n")
        self.script = self.home / "install-prompt.sh"
        template = (ROOT / "run_onchange_after_20-install-fish-plugins.sh.tmpl").read_text()
        # The only template expression is a comment containing the plugin hash.
        template = template.replace(
            'eval "$(/opt/homebrew/bin/brew shellenv)"', ": # Homebrew stub",
        )
        self.script.write_text(template)

    def install(self):
        return subprocess.run(
            ["/bin/bash", str(self.script)], env=self.env,
            capture_output=True, text=True, timeout=15,
        )

    def test_configures_after_installer_exits_and_tolerates_repeat_runs(self):
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(self.omf.exists())
            self.assertFalse(self.loader.exists())
        self.assertEqual(self.calls.read_text().splitlines(), ["fisher", "tide"] * 2)

    def test_failed_install_keeps_old_loader_and_skips_configuration(self):
        self.env["TEST_INSTALL_STATUS"] = "7"
        result = self.install()
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), ["fisher"])
        self.assertTrue(self.omf.exists())
        self.assertTrue(self.loader.exists())

    def test_missing_plugin_is_reported_even_if_fisher_exits_successfully(self):
        self.env["TEST_PLUGIN_PRESENT"] = "0"
        result = self.install()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), ["fisher"])
        self.assertTrue(self.loader.exists())

    def test_failed_configuration_keeps_old_loader(self):
        self.env["TEST_CONFIGURE_STATUS"] = "9"
        result = self.install()
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), ["fisher", "tide"])
        self.assertTrue(self.omf.exists())
        self.assertTrue(self.loader.exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
