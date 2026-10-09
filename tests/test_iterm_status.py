import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import shlex
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'private_dot_config/iterm2/codex-status.py'
spec = importlib.util.spec_from_file_location('codex_status', SCRIPT)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
TERMINAL = '11111111-1111-4111-8111-111111111111'


def event(name, **fields):
    return dict(session_id='root', cwd='/work/example', hook_event_name=name, **fields)


class LifecycleTests(unittest.TestCase):
    def start(self):
        return hook.transition({}, event('SessionStart', source='startup'))

    def test_lifecycle_and_compaction(self):
        state = self.start()
        self.assertEqual(state['status'], 'idle')
        state = hook.transition(state, event('PreCompact', trigger='manual'))
        self.assertEqual(state['status'], 'idle')
        state = hook.transition(state, event('UserPromptSubmit', turn_id='1'))
        self.assertEqual(state['status'], 'working')
        state = hook.transition(state, event('SessionStart', source='compact'))
        self.assertEqual(state['status'], 'working')
        state = hook.transition(state, event('Stop', turn_id='1'))
        self.assertEqual(state['status'], 'idle')
        state = hook.transition(state, event('SessionEnd'))
        self.assertEqual((state['status'], state['detail']), ('', ''))
        self.assertIsNone(hook.transition(state, event('PreToolUse', tool_name='Bash')))

    def test_parallel_approvals_and_matching_description(self):
        state = hook.transition(self.start(), event('UserPromptSubmit', turn_id='1'))
        for cmd in ['first', 'second']:
            state = hook.transition(state, event('PermissionRequest', turn_id='1', tool_name='Bash',
                                                tool_input={'command': cmd, 'description': 'reason'}))
        state = hook.transition(state, event('PostToolUse', turn_id='1', tool_name='Bash',
                                            tool_input={'command': 'first'}))
        self.assertEqual(state['status'], 'waiting')
        self.assertEqual(len(state['pending']), 1)
        state = hook.transition(state, event('PostToolUse', turn_id='1', tool_name='Bash',
                                            tool_input={'command': 'second'}))
        self.assertEqual(state['status'], 'working')

    def test_input_and_new_prompt_clear_waiting(self):
        state = hook.transition(self.start(), event('PreToolUse', tool_name='functions.request_user_input',
                                                    tool_input={'questions': ['secret']}))
        self.assertEqual(state['status'], 'waiting')
        state = hook.transition(state, event('UserPromptSubmit', turn_id='new'))
        self.assertEqual(state['status'], 'working')
        self.assertEqual(state['pending'], {})

    def test_old_turn_cannot_clear_new_turn(self):
        state = hook.transition(self.start(), event('UserPromptSubmit', turn_id='new'))
        for name in ['Stop', 'Interrupt', 'PostToolUse', 'PermissionRequest']:
            self.assertIsNone(hook.transition(state, event(name, turn_id='old')))

    def test_child_thread_cannot_overwrite_root(self):
        state = self.start()
        for name in ['SessionStart', 'PreToolUse', 'Stop', 'SessionEnd']:
            other = event(name)
            other['session_id'] = 'child'
            self.assertIsNone(hook.transition(state, other))

    def test_background_agents_outlive_parent_turn(self):
        state = hook.transition(self.start(), event('UserPromptSubmit', turn_id='old'))
        state = hook.transition(state, event('SubagentStart', agent_id='child', turn_id='old'))
        state = hook.transition(state, event('Stop', turn_id='old'))
        self.assertEqual(state['status'], 'working')
        state = hook.transition(state, event('UserPromptSubmit', turn_id='new'))
        state = hook.transition(state, event('Stop', turn_id='new'))
        state = hook.transition(state, event('SubagentStop', agent_id='child', turn_id='old'))
        self.assertEqual(state['status'], 'idle')
        self.assertEqual(state['agents'], [])

    def test_interrupt_clears_pending_and_agents(self):
        state = hook.transition(self.start(), event('SubagentStart', agent_id='child'))
        state = hook.transition(state, event('PermissionRequest', tool_name='Bash', tool_input={}))
        state = hook.transition(state, event('Interrupt'))
        self.assertEqual((state['status'], state['pending'], state['agents']), ('idle', {}, []))

    def test_metadata_only(self):
        state = hook.transition(self.start(), event('PermissionRequest', tool_name='Bash',
            tool_input={'command': 'super-secret-command', 'description': 'super-secret-reason'},
            prompt='super-secret-prompt', tool_response='super-secret-response'))
        self.assertNotIn('super-secret', json.dumps(state))

    def test_terminal_validation(self):
        self.assertEqual(hook.terminal_id('w0t0p0:' + TERMINAL.lower()), TERMINAL)
        for invalid in ['', 'active', '../other', 'w0t0p0', TERMINAL + ';malicious']:
            self.assertIsNone(hook.terminal_id(invalid))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'CODEX_ITERM2_TAB': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.binary = patch.object(hook, 'find_it2', return_value=Path('/fake/it2'))
        self.binary.start()
        self.addCleanup(self.binary.stop)

    def test_new_launcher_target_replaces_binding_to_closed_tab(self):
        old = '22222222-2222-4222-8222-222222222222'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
            TERM_PROGRAM='iTerm.app', ITERM_SESSION_ID=old,
            CODEX_ITERM2_TAB='w0t0p0:' + TERMINAL, XDG_CACHE_HOME=tmp):
            data = Path(tmp) / 'codex-iterm-status'
            data.mkdir()
            hook.save_state(data / 'targets.json', {'root': old})
            with patch.object(hook.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                hook.report(event('SessionStart', source='resume'))
                args = run.call_args.args[0]
                self.assertEqual(args[args.index('--session') + 1], TERMINAL)
            self.assertEqual(hook.read_state(data / 'targets.json')['root'], TERMINAL)

    def test_bound_thread_uses_explicit_terminal_instead_of_stale_environment(self):
        target = '22222222-2222-4222-8222-222222222222'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
            TERM_PROGRAM='iTerm.app', ITERM_SESSION_ID=TERMINAL, XDG_CACHE_HOME=tmp):
            data = Path(tmp) / 'codex-iterm-status'
            data.mkdir()
            hook.save_state(data / (TERMINAL + '.json'), hook.transition({}, event('SessionStart')))
            with patch.object(hook.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                with patch.dict(os.environ, ITERM_SESSION_ID=target), patch('sys.stdout', io.StringIO()):
                    hook.bind('root')
                hook.report(event('PreToolUse', tool_name='Bash'))
                args = run.call_args.args[0]
                self.assertEqual(args[args.index('--session') + 1], target)
            self.assertTrue(hook.read_state(data / (target + '.json'))['reported'])

    def test_always_returns_empty_json(self):
        env = dict(os.environ, TERM_PROGRAM='other', ITERM_SESSION_ID='')
        for payload in ['bad json', '[]', '{}', json.dumps(event('Stop'))]:
            result = subprocess.run(['/usr/bin/python3', str(SCRIPT)], input=payload, text=True,
                                    capture_output=True, env=env, timeout=3)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '{}\n', ''))

    def test_gui_failure_is_observational(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
            TERM_PROGRAM='iTerm.app', ITERM_SESSION_ID=TERMINAL, XDG_CACHE_HOME=tmp):
            with patch.object(hook.subprocess, 'run', side_effect=OSError('no GUI')), \
                 patch.object(hook.sys, 'stdin', io.StringIO(json.dumps(event('SessionStart')))), \
                 patch.object(hook.sys, 'stdout', io.StringIO()) as output:
                hook.main()
                self.assertEqual(output.getvalue(), '{}\n')
            state = json.loads((Path(tmp) / 'codex-iterm-status' / (TERMINAL + '.json')).read_text())
            self.assertFalse(state['reported'])

    def test_simultaneous_gui_reports_send_latest_revision(self):
        entered, release = threading.Event(), threading.Event()
        calls, errors = [], []
        def fake_run(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(1))
            return subprocess.CompletedProcess(args, 0)
        def report(payload):
            try:
                hook.report(payload)
            except Exception as exc:
                errors.append(exc)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
            TERM_PROGRAM='iTerm.app', ITERM_SESSION_ID='w0t0p0:' + TERMINAL, XDG_CACHE_HOME=tmp), \
            patch.object(hook.subprocess, 'run', side_effect=fake_run):
            path = Path(tmp) / 'codex-iterm-status' / (TERMINAL + '.json')
            first = threading.Thread(target=report, args=(event('SessionStart'),))
            first.start()
            self.assertTrue(entered.wait(1))
            second = threading.Thread(target=report, args=(event('UserPromptSubmit', turn_id='1'),))
            second.start()
            for _ in range(100):
                if hook.read_state(path).get('revision') == 2:
                    break
                release.wait(0.005)
            self.assertEqual(hook.read_state(path)['revision'], 2)
            release.set()
            first.join(2)
            second.join(2)
            self.assertFalse(errors)
            self.assertEqual(calls[-1][calls[-1].index('--status') + 1], 'working')
            self.assertEqual(calls[-1][calls[-1].index('--session') + 1], TERMINAL)
            self.assertTrue(hook.read_state(path)['reported'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ClaudeColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'private_dot_config/iterm2/executable_cc-status-green.py'
        spec = importlib.util.spec_from_file_location('claude_green', path)
        cls.claude = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.claude)

    def test_idle_text_does_not_override_running_background_work(self):
        payload = {'hook_event_name': 'Stop', 'background_tasks': [{'status': 'running'}]}
        self.assertFalse(self.claude.becomes_idle(payload, lambda: 0))
        payload['background_tasks'][0]['status'] = 'completed'
        self.assertTrue(self.claude.becomes_idle(payload, lambda: 0))

    def test_idle_notification_uses_stored_background_count(self):
        payload = {'hook_event_name': 'Notification', 'notification_type': 'idle_prompt'}
        self.assertFalse(self.claude.becomes_idle(payload, lambda: 1))
        self.assertTrue(self.claude.becomes_idle(payload, lambda: 0))

    def test_subagent_stop_leaves_native_status_unchanged(self):
        self.assertFalse(self.claude.becomes_idle({'hook_event_name': 'SubagentStop'}, lambda: 0))

    def native_command(self, argv):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1)
        stdin = io.TextIOWrapper(io.BytesIO(b'{}'))
        with patch.object(self.claude.subprocess, 'run', run), \
             patch('sys.argv', ['cc-status-green.py'] + argv), patch('sys.stdin', stdin):
            self.claude.main()
        return calls[0][0]

    def test_runs_cc_status_named_by_hook_or_bundled_fallback(self):
        bundled = str(self.claude.UTILITIES / 'cc-status')
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'cc-status'
            self.assertEqual(self.native_command([str(link)]), bundled)
            link.write_text('')
            self.assertEqual(self.native_command([str(link)]), str(link))
        self.assertEqual(self.native_command([]), bundled)


class FishLauncherTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('fish'), 'fish is required')
    def test_resume_gets_current_tab_without_duplicate_no_daemon(self):
        wrapper = Path(__file__).resolve().parents[1] / 'private_dot_config/private_fish/functions/codex.fish'
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'codex'
            fake.write_text('#!/usr/bin/python3\nimport os,sys,json\nprint(json.dumps([sys.argv[1:], os.environ.get("CODEX_ITERM2_TAB")]))\n')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'],
                       TERM_PROGRAM='iTerm.app', ITERM_SESSION_ID='w0t0p0:' + TERMINAL)
            for arguments in ('resume --last', '--no-daemon resume --last'):
                result = subprocess.run([shutil.which('fish'), '--no-config', '-c',
                    'source ' + shlex.quote(str(wrapper)) + '; codex ' + arguments],
                    env=env, capture_output=True, text=True, check=True)
                argv, target = json.loads(result.stdout)
                self.assertEqual(argv, ['--no-daemon', 'resume', '--last'])
                self.assertEqual(target, env['ITERM_SESSION_ID'])
            env['TERM_PROGRAM'] = 'other'
            result = subprocess.run([shutil.which('fish'), '--no-config', '-c',
                'source ' + shlex.quote(str(wrapper)) + '; codex resume --last'],
                env=env, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)[0], ['resume', '--last'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
