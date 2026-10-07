"""Port validation, Git pickers, and atomic init-cache regression checks."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import unittest

from test_reliability import FISH, FishTest, ROOT

FUNCTIONS = ROOT / "private_dot_config/private_fish/dot_fish_functions"
GIT = shutil.which("git")


class PortTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "port-calls"
        self.env.update(
            TEST_PORT_CALLS=str(self.calls), TEST_PIDS="111\n222\n",
            TEST_LSOF_STATUS="0", TEST_KILL_STATUS="0",
        )
        stub = self.bin / "port-stub"
        stub.write_text("""#!/bin/sh
tool=$1
shift
printf '%s\n' "$tool $*" >> "$TEST_PORT_CALLS"
if [ "$tool" = lsof ]; then
    printf '%s' "$TEST_PIDS"
    exit "$TEST_LSOF_STATUS"
fi
exit "$TEST_KILL_STATUS"
""")
        stub.chmod(0o700)
        self.prelude = f"""source {shlex.quote(str(FUNCTIONS))}
function lsof; command {shlex.quote(str(stub))} lsof $argv; end
function kill; command {shlex.quote(str(stub))} kill $argv; end
"""

    def call(self, function, *args):
        return self.run_fish(self.prelude + f"{function} {shlex.join(args)}")

    def test_invalid_ports_never_query_or_kill_processes(self):
        for args in [(), ("0",), ("65536",), ("abc",), ("-1",), ("8e2",),
                     ("12345678901234567890",), ("80 81",), ("80", "81")]:
            for function in ["findbyport", "killbyport"]:
                with self.subTest(function=function, args=args):
                    result = self.call(function, *args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("PORT (1-65535)", result.stderr)
                    self.assertFalse(self.calls.exists())

    def test_valid_ports_are_passed_to_lsof(self):
        for port in ["1", "80", "65535"]:
            with self.subTest(port=port):
                self.calls.unlink(missing_ok=True)
                result = self.call("findbyport", port)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "111\n222\n")
                self.assertEqual(self.calls.read_text(), f"lsof -ti tcp:{port} -sTCP:LISTEN\n")

    def test_kill_uses_only_returned_pids(self):
        result = self.call("killbyport", "80")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), [
            "lsof -ti tcp:80 -sTCP:LISTEN", "kill -9 111 222",
        ])

    def test_no_listeners_does_not_kill(self):
        self.env.update(TEST_PIDS="", TEST_LSOF_STATUS="1")
        result = self.call("killbyport", "80")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Nothing listening on port 80", result.stdout)
        self.assertNotIn("kill", self.calls.read_text())

    def test_lookup_errors_and_partial_results_do_not_kill(self):
        for status in ["1", "2", "127"]:
            with self.subTest(status=status):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_LSOF_STATUS"] = status
                result = self.call("killbyport", "80")
                self.assertEqual(result.returncode, int(status), result.stderr)
                self.assertNotIn("kill", self.calls.read_text())

    def test_kill_failure_propagates(self):
        self.env["TEST_KILL_STATUS"] = "4"
        self.assertEqual(self.call("killbyport", "80").returncode, 4)


@unittest.skipUnless(GIT, "git is required")
class GitHelperTests(FishTest):
    def setUp(self):
        super().setUp()
        self.env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        self.repo = self.home / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet", "-b", "main")
        self.file = self.repo / "example"
        self.file.write_text("base\n")
        self.commit("Shared commit")
        wrapper = self.bin / "git"
        wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(GIT)} "$@"\n')
        wrapper.chmod(0o700)
        self.picker_input = self.home / "picker-input"
        self.env.update(TEST_PICKER_INPUT=str(self.picker_input), TEST_REF="refs/heads/main", TEST_CANCEL="0")
        picker = self.bin / "fzf"
        picker.write_text("""#!/bin/sh
cat > "$TEST_PICKER_INPUT"
if [ "$TEST_CANCEL" = 1 ]; then exit 130; fi
awk -F '\t' -v ref="$TEST_REF" '$2 == ref {print; exit}' "$TEST_PICKER_INPUT"
""")
        picker.chmod(0o700)

    def git(self, *args):
        return subprocess.run(
            [GIT, *args], cwd=self.repo, env=self.env, capture_output=True,
            text=True, check=True, timeout=15,
        ).stdout.strip()

    def commit(self, message):
        self.git("add", "example")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", message)

    def call(self, function):
        return self.run_fish(
            f"cd {shlex.quote(str(self.repo))}; source {shlex.quote(str(FUNCTIONS))}; {function}"
        )

    def test_gitu_excludes_similarly_named_branches(self):
        self.git("branch", "main-extra")
        result = self.call("gitu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.file.write_text("unique\n")
        self.commit("Unique commit")
        result = self.call("gitu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Unique commit", result.stdout)
        self.assertNotIn("Shared commit", result.stdout)

    def test_gitu_handles_literal_regex_characters(self):
        self.git("branch", "-m", "feature.v2")
        self.git("branch", "featureXv2")
        result = self.call("gitu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_gitu_with_no_other_branches(self):
        result = self.call("gitu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Shared commit", result.stdout)

    def test_fco_current_branch_has_no_star(self):
        result = self.call("fco")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")
        self.assertIn("main\trefs/heads/main", self.picker_input.read_text())
        self.assertNotIn("* main", self.picker_input.read_text())

    def test_fco_remote_creates_tracking_branch_and_skips_symbolic_head(self):
        self.git("remote", "add", "origin", "../unused")
        self.git("update-ref", "refs/remotes/origin/topic", "HEAD")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/topic")
        self.env["TEST_REF"] = "refs/remotes/origin/topic"
        result = self.call("fco")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "topic")
        self.assertEqual(self.git("config", "branch.topic.remote"), "origin")
        self.assertEqual(self.git("config", "branch.topic.merge"), "refs/heads/topic")
        self.assertNotIn("refs/remotes/origin/HEAD", self.picker_input.read_text())

    def test_fco_cancellation_keeps_branch(self):
        self.env["TEST_CANCEL"] = "1"
        result = self.call("fco")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")

    def test_fco_preserves_uncommitted_changes_when_switch_fails(self):
        self.git("switch", "--quiet", "-c", "topic")
        self.file.write_text("topic\n")
        self.commit("Topic commit")
        self.git("switch", "--quiet", "main")
        self.file.write_text("uncommitted\n")
        self.env["TEST_REF"] = "refs/heads/topic"
        result = self.call("fco")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(self.file.read_text(), "uncommitted\n")


class InitCacheTests(FishTest):
    def setUp(self):
        super().setUp()
        config = (ROOT / "private_dot_config/private_fish/config.fish").read_text()
        self.helper = config[
            config.index("    function __cached_init"):
            config.index("    # fzf before atuin")
        ]
        self.cache = self.home / ".cache/fish/init-mock-init.fish"
        self.generator = self.bin / "mock-init"
        self.generator.write_text("""#!/bin/sh
if [ "${TEST_INIT_FAILURE:-0}" != 0 ]; then exit "$TEST_INIT_FAILURE"; fi
printf 'function mock_init; echo ready; end\n'
""")
        self.generator.chmod(0o700)
        self.call = self.helper + "__cached_init mock-init --fish"

    def test_generation_and_reuse(self):
        result = self.run_fish(self.call)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), self.cache)
        previous = (self.cache.read_bytes(), self.cache.stat().st_mtime_ns)
        result = self.run_fish(self.call)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(previous, (self.cache.read_bytes(), self.cache.stat().st_mtime_ns))
        result = self.run_fish(f"source {shlex.quote(str(self.cache))}; mock_init")
        self.assertEqual(result.stdout, "ready\n")

    def test_generator_failure_does_not_replace_previous_cache(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("# old\nfunction mock_init; echo old; end\n")
        previous = self.cache.read_bytes()
        self.env["TEST_INIT_FAILURE"] = "7"
        result = self.run_fish(self.call)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.cache.read_bytes(), previous)
        self.assertEqual(list(self.cache.parent.glob("init-mock-init.fish.*")), [])

    def test_readers_see_previous_complete_cache_during_write(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("# old\nfunction mock_init; echo old; end\n")
        previous = self.cache.read_bytes()
        started = self.home / "prefix-written"
        release = self.home / "release-write"
        self.env.update(TEST_PREFIX_WRITTEN=str(started), TEST_RELEASE_WRITE=str(release))
        # Pause after writing the header to exercise the publication boundary.
        slow_printf = """function printf
    builtin printf '%s\\n' $argv[2]
    command touch $TEST_PREFIX_WRITTEN
    for attempt in (seq 1 500)
        test -f $TEST_RELEASE_WRITE; and break
        command sleep 0.01
    end
    builtin printf '%s\\n' $argv[3..-1]
end
"""
        process = subprocess.Popen(
            [FISH, "--no-config", "-c", slow_printf + self.call],
            env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 5
            while not started.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(0.01)
            self.assertTrue(started.exists())
            self.assertEqual(self.cache.read_bytes(), previous)
            result = self.run_fish(f"source {shlex.quote(str(self.cache))}; mock_init")
            self.assertEqual(result.stdout, "old\n")
            release.touch()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(Path(stdout.strip()), self.cache)
            result = self.run_fish(f"source {shlex.quote(str(self.cache))}; mock_init")
            self.assertEqual(result.stdout, "ready\n")
            self.assertEqual(list(self.cache.parent.glob("init-mock-init.fish.*")), [])
        finally:
            release.touch()
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    unittest.main()
