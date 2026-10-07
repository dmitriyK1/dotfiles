"""Sleep, remote Git comparison, and directory helper regression checks."""

from pathlib import Path
import shlex
import shutil
import unittest

from test_reliability import FishTest, ROOT

FUNCTIONS = ROOT / "private_dot_config/private_fish/dot_fish_functions"
SLEEP_FUNCTION = ROOT / "private_dot_config/private_fish/functions/toggle-sleep.fish"
JQ = shutil.which("jq")
RG = shutil.which("rg")


@unittest.skipUnless(RG, "rg is required")
class PathPickerTests(FishTest):
    def setUp(self):
        super().setUp()
        self.directory = self.home / "path with spaces and 'quotes'"
        self.directory.mkdir()
        self.filename = "tool with spaces"
        (self.directory / self.filename).write_text("example\n")
        self.calls = self.home / "picker-calls"
        self.env.update(
            PATH=f"{self.directory}:{self.env['PATH']}",
            TEST_PICKER_CALLS=str(self.calls), TEST_DIRECTORY=str(self.directory),
            TEST_FILENAME=self.filename, TEST_CANCEL="",
        )
        rg = self.bin / "rg"
        rg.write_text(f'#!/bin/sh\nexec {shlex.quote(RG)} "$@"\n')
        rg.chmod(0o700)
        picker = self.bin / "fzf"
        picker.write_text("""#!/bin/sh
printf '%s\n' "$*" >> "$TEST_PICKER_CALLS"
case "$*" in
    *'[find:path]'*) stage=directory; choice=$TEST_DIRECTORY ;;
    *) stage=file; choice=$TEST_FILENAME ;;
esac
cat > "$TEST_PICKER_CALLS.$stage"
if [ "$TEST_CANCEL" = "$stage" ]; then exit 130; fi
grep -Fx -- "$choice" "$TEST_PICKER_CALLS.$stage"
""")
        picker.chmod(0o700)

    def pick(self):
        return self.run_fish(f"source {shlex.quote(str(FUNCTIONS))}\nfp")

    def test_directory_and_filename_are_preserved(self):
        result = self.pick()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.filename + "\n")
        self.assertIn(str(self.directory), Path(str(self.calls) + ".directory").read_text().splitlines())
        self.assertEqual(Path(str(self.calls) + ".file").read_text(), self.filename + "\n")

    def test_cancellation_exits_without_reopening_picker(self):
        for stage, count in [("directory", 1), ("file", 2)]:
            with self.subTest(stage=stage):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_CANCEL"] = stage
                result = self.pick()
                self.assertEqual(result.returncode, 130, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(self.calls.read_text().splitlines()), count)


@unittest.skipUnless(JQ, "jq is required")
class BuildStatusTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "aws-calls"
        self.env.update(
            TEST_AWS_CALLS=str(self.calls), TEST_LIST_STATUS="0", TEST_BATCH_STATUS="0",
            TEST_LIST_OUTPUT='{"ids":["project:build-id"]}',
            TEST_BATCH_OUTPUT='{"builds":[{"phases":[{"phaseType":"BUILD","phaseStatus":"SUCCEEDED"}]}]}',
        )
        jq = self.bin / "jq"
        jq.write_text(f'#!/bin/sh\nexec {shlex.quote(JQ)} "$@"\n')
        jq.chmod(0o700)
        aws = self.bin / "aws"
        aws.write_text("""#!/bin/sh
printf '%s\n' "$*" >> "$TEST_AWS_CALLS"
if [ "$2" = list-builds-for-project ]; then
    printf '%s\n' "$TEST_LIST_OUTPUT"
    exit "$TEST_LIST_STATUS"
fi
printf '%s\n' "$TEST_BATCH_OUTPUT"
exit "$TEST_BATCH_STATUS"
""")
        aws.chmod(0o700)

    def build_status(self, *args):
        return self.run_fish(f"source {shlex.quote(str(FUNCTIONS))}\nbuild_status {shlex.join(args)}")

    def test_default_and_explicit_project(self):
        for args, project in [((), "lwa-ui-dev-build"), (("custom-project",), "custom-project")]:
            with self.subTest(args=args):
                self.calls.unlink(missing_ok=True)
                result = self.build_status(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, project + '\n"SUCCEEDED"\n')
                self.assertEqual(self.calls.read_text().splitlines(), [
                    f"codebuild list-builds-for-project --project-name {project}",
                    "codebuild batch-get-builds --ids project:build-id",
                ])

    def test_invalid_arguments_do_not_query_aws(self):
        for args in [("",), ("one", "two")]:
            with self.subTest(args=args):
                result = self.build_status(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("usage: build_status", result.stderr)
                self.assertFalse(self.calls.exists())

    def test_failed_list_does_not_fetch_build_even_with_partial_output(self):
        self.env["TEST_LIST_STATUS"] = "7"
        result = self.build_status()
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(len(self.calls.read_text().splitlines()), 1)

    def test_empty_or_invalid_response_does_not_fetch_build(self):
        for output in ['{"ids":[]}', '{}', '{"ids":[null]}', '{"ids":[""]}',
                       '{"ids":[123]}', 'invalid json']:
            with self.subTest(output=output):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_LIST_OUTPUT"] = output
                result = self.build_status()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("could not find a build ID", result.stderr)
                self.assertEqual(len(self.calls.read_text().splitlines()), 1)

    def test_batch_aws_and_json_errors_propagate(self):
        self.env["TEST_BATCH_STATUS"] = "9"
        result = self.build_status()
        self.assertEqual(result.returncode, 9, result.stderr)
        self.env.update(TEST_BATCH_STATUS="0", TEST_BATCH_OUTPUT="invalid json")
        result = self.build_status()
        self.assertNotEqual(result.returncode, 0)


class SleepTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "sleep-calls"
        self.env.update(
            TEST_SLEEP_CALLS=str(self.calls), TEST_PMSET_STATUS="0",
            TEST_POWER_SETTINGS=" SleepDisabled 0\n", TEST_SUDO_STATUS="0",
        )
        stub = self.bin / "sleep-stub"
        stub.write_text("""#!/bin/sh
tool=${0##*/}
printf '%s\n' "$tool $*" >> "$TEST_SLEEP_CALLS"
if [ "$tool" = pmset ]; then
    printf '%s' "$TEST_POWER_SETTINGS"
    exit "$TEST_PMSET_STATUS"
fi
exit "$TEST_SUDO_STATUS"
""")
        stub.chmod(0o700)
        for name in ["pmset", "sudo"]:
            (self.bin / name).symlink_to(stub)

    def toggle(self):
        return self.run_fish(f"source {shlex.quote(str(SLEEP_FUNCTION))}\ntoggle-sleep")

    def test_failed_queries_never_change_power_settings(self):
        for output in ["", " SleepDisabled 1\n"]:
            with self.subTest(output=output):
                self.env.update(TEST_PMSET_STATUS="7", TEST_POWER_SETTINGS=output)
                result = self.toggle()
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(self.calls.read_text(), "pmset -g\n")
                self.assertEqual(result.stdout, "")
                self.calls.unlink()

    def test_toggle_and_missing_flag_keep_existing_semantics(self):
        for output, value, message in [
            (" SleepDisabled 1\n", "0", "Sleep enabled"),
            (" SleepDisabled 0\n", "1", "Sleep disabled"),
            (" sleep 1\n", "1", "Sleep disabled"),
        ]:
            with self.subTest(output=output):
                self.env["TEST_POWER_SETTINGS"] = output
                result = self.toggle()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls.read_text().splitlines(), [
                    "pmset -g", f"sudo pmset -a disablesleep {value}",
                ])
                self.assertIn(message, result.stdout)
                self.calls.unlink()

    def test_failed_changes_do_not_report_success(self):
        self.env["TEST_SUDO_STATUS"] = "5"
        for value in ["0", "1"]:
            with self.subTest(value=value):
                self.env["TEST_POWER_SETTINGS"] = f" SleepDisabled {value}\n"
                result = self.toggle()
                self.assertEqual(result.returncode, 5, result.stderr)
                self.assertEqual(result.stdout, "")


class RemoteComparisonTests(FishTest):
    def setUp(self):
        super().setUp()
        self.calls = self.home / "git-comparison-calls"
        self.env.update(
            TEST_GIT_CALLS=str(self.calls), TEST_FETCH_STATUS="0", TEST_COMPARE_STATUS="0",
        )
        stub = self.bin / "git"
        stub.write_text("""#!/bin/sh
printf '%s\n' "$*" >> "$TEST_GIT_CALLS"
if [ "$1" = fetch ]; then exit "$TEST_FETCH_STATUS"; fi
printf 'comparison output\n'
exit "$TEST_COMPARE_STATUS"
""")
        stub.chmod(0o700)

    def compare(self, function, *args):
        return self.run_fish(
            f"source {shlex.quote(str(FUNCTIONS))}\n{function} {shlex.join(args)}"
        )

    def test_invalid_arguments_never_fetch(self):
        for function in ["gdrb", "glrb"]:
            for args in [(), ("",), ("main", "other")]:
                with self.subTest(function=function, args=args):
                    result = self.compare(function, *args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(f"usage: {function} BRANCH", result.stderr)
                    self.assertFalse(self.calls.exists())

    def test_fetch_failure_never_compares_stale_refs(self):
        self.env["TEST_FETCH_STATUS"] = "7"
        for function in ["gdrb", "glrb"]:
            with self.subTest(function=function):
                result = self.compare(function, "main")
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.calls.read_text(), "fetch origin\n")
                self.calls.unlink()

    def test_successful_fetch_compares_requested_branch_and_propagates_status(self):
        for function, subcommand in [("gdrb", "diff"), ("glrb", "log")]:
            for status in [0, 9]:
                with self.subTest(function=function, status=status):
                    self.env["TEST_COMPARE_STATUS"] = str(status)
                    result = self.compare(function, "topic/example")
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertEqual(result.stdout, "comparison output\n")
                    self.assertEqual(self.calls.read_text().splitlines(), [
                        "fetch origin", f"{subcommand} ...origin/topic/example",
                    ])
                    self.calls.unlink()


class MkcdTests(FishTest):
    def setUp(self):
        super().setUp()
        self.workspace = self.home / "work"
        self.workspace.mkdir()
        self.calls = self.home / "cd-calls"
        self.env["TEST_CD_CALLS"] = str(self.calls)
        self.prelude = f"""source {shlex.quote(str(FUNCTIONS))}
builtin cd -- {shlex.quote(str(self.workspace))}
function cd
    printf '%s\\n' "$argv" >> "$TEST_CD_CALLS"
    builtin cd $argv
end
"""

    def create_and_enter(self, *args):
        return self.run_fish(self.prelude + f"""mkcd {shlex.join(args)}
set -l result_status $status
printf '%s\\n' "$PWD"
exit $result_status
""")

    def test_invalid_arguments_do_not_create_directories_or_change_cwd(self):
        for args in [(), ("",), ("first", "second")]:
            with self.subTest(args=args):
                result = self.create_and_enter(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("usage: mkcd DIRECTORY", result.stderr)
                self.assertEqual(Path(result.stdout.strip()).resolve(), self.workspace.resolve())
                self.assertEqual(list(self.workspace.iterdir()), [])
                self.assertFalse(self.calls.exists())

    def test_mkdir_failure_never_calls_cd(self):
        (self.workspace / "blocked").write_text("file, not directory\n")
        result = self.create_and_enter("blocked/child")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(Path(result.stdout.strip()).resolve(), self.workspace.resolve())
        self.assertFalse(self.calls.exists())

    def test_spaces_leading_dash_and_existing_directories(self):
        for directory in ["nested/dir with spaces", "-leading-dash"]:
            for attempt in range(2):
                with self.subTest(directory=directory, attempt=attempt):
                    result = self.create_and_enter(directory)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    target = self.workspace / directory
                    self.assertTrue(target.is_dir())
                    self.assertEqual(Path(result.stdout.splitlines()[-1]).resolve(), target.resolve())


if __name__ == "__main__":
    unittest.main()
