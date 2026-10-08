import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1] / 'private_dot_config/iterm2/install-codex-status.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class MigrationTests(unittest.TestCase):
    def fixture(self, home):
        for folder in ['.config/iterm2', '.codex', '.agents/plugins',
                       'Library/Application Support/iTerm2/DynamicProfiles', '.config/codex-iterm2-status']:
            (home / folder).mkdir(parents=True)
        for name in ['codex-status.py', 'codex-launch.sh']:
            (home / '.config/iterm2' / name).write_text('placeholder')
        config = '[tui]\nstatus_line_use_colors = true\n\n[plugins."other@personal"]\nenabled = true\n\n[plugins."iterm2-status@personal"]\nenabled = true\n\n[hooks.state."iterm2-status@personal:hooks/hooks.json:stop:0:0"]\ntrusted_hash = "old"\n\n[hooks.state."other:stop:0:0"]\ntrusted_hash = "keep"\n'
        (home / '.codex/config.toml').write_text(config)
        self.other_hook = {'hooks': [{'type': 'command', 'command': 'other-hook'}]}
        (home / '.codex/hooks.json').write_text(json.dumps({'description': 'keep', 'hooks': {'Stop': [self.other_hook]}}))
        (home / '.agents/plugins/marketplace.json').write_text(json.dumps({'name': 'personal', 'plugins': [
            {'name': 'iterm2-status'}, {'name': 'other'}]}))
        self.profiles = home / 'Library/Application Support/iTerm2/DynamicProfiles/codex-profiles.json'
        self.other_profile = {'Guid': 'other', 'Command': 'keep', 'Tags': ['other']}
        self.profiles.write_text(json.dumps({'Profiles': [
            {'Guid': 'CODEX-ITERM2-DEFAULT-0001', 'Name': 'Codex', 'Command': 'old',
             'Tags': ['iterm2-status', 'ai'], 'Font': 'keep-font'}, self.other_profile]}))
        (home / '.config/codex-iterm2-status/settings.json').write_text('{"old":"keep in backup"}')

    def test_migration_preserves_unrelated_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.fixture(home)
            calls = []
            def runner(args, **kwargs):
                calls.append(args)
                if 'list' in args:
                    return subprocess.CompletedProcess(args, 0, json.dumps({'installed': [{'pluginId': installer.SELECTOR}]}))
                # Simulate Codex modifying its own config during uninstall.
                config = home / '.codex/config.toml'
                config.write_text(config.read_text() + '\n[extra]\nvalue = 7\n')
                return subprocess.CompletedProcess(args, 0)
            with patch.object(installer.shutil, 'which', return_value='/fake/codex'), \
                 patch('sys.stdout', io.StringIO()):
                installer.install(home, run=runner)
            text = (home / '.codex/config.toml').read_text()
            self.assertNotIn('iterm2-status', text)
            self.assertIn('other@personal', text)
            self.assertIn('trusted_hash = "keep"', text)
            self.assertIn('value = 7', text)
            hooks = json.loads((home / '.codex/hooks.json').read_text())
            self.assertEqual(hooks['description'], 'keep')
            self.assertIn(self.other_hook, hooks['hooks']['Stop'])
            self.assertEqual(len(hooks['hooks']), 12)
            self.assertEqual(json.loads((home / '.agents/plugins/marketplace.json').read_text())['plugins'], [{'name': 'other'}])
            profiles = json.loads(self.profiles.read_text())['Profiles']
            self.assertEqual(profiles[1], self.other_profile)
            self.assertEqual(profiles[0]['Font'], 'keep-font')
            self.assertNotIn('iterm2-status', profiles[0]['Command'])
            self.assertIn('codex-launch.sh', profiles[0]['Command'])
            self.assertFalse((home / '.config/codex-iterm2-status').exists())
            self.assertTrue(list((home / '.config/iterm2/backups').glob('*/old-runtime/settings.json')))
            plan = installer.build_plan(home)
            for path, value in plan.items():
                self.assertEqual(path.read_text(), value)
            self.assertEqual(calls[-1][1:4], ['plugin', 'remove', installer.SELECTOR])

    def test_dry_run_does_not_change_files_or_call_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.fixture(home)
            before = {str(p): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            with patch('sys.stdout', io.StringIO()):
                installer.install(home, dry_run=True, run=lambda *a, **kw: self.fail('CLI called'))
            after = {str(p): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            self.assertEqual(before, after)

    def test_invalid_existing_hooks_abort_before_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.fixture(home)
            (home / '.codex/hooks.json').write_text('invalid')
            with self.assertRaises(ValueError):
                installer.install(home)
            self.assertIn('iterm2-status', (home / '.codex/config.toml').read_text())


    def test_fresh_home_registers_both_agents_without_old_marketplace(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / '.config/iterm2').mkdir(parents=True)
            for name in ('codex-status.py', 'codex-launch.sh'):
                (home / '.config/iterm2' / name).write_text('placeholder')
            with patch.object(installer.shutil, 'which', return_value='/fake/codex'), patch('sys.stdout', io.StringIO()):
                installer.install(home, run=lambda *a, **kw: self.fail('No old plugin CLI call expected'))
            hooks = json.loads((home / '.codex/hooks.json').read_text())
            self.assertEqual(len(hooks['hooks']), 12)
            claude = json.loads((home / '.claude/settings.json').read_text())
            self.assertEqual(len(claude['hooks']), 10)
            profiles = json.loads((home / 'Library/Application Support/iTerm2/DynamicProfiles/codex-profiles.json').read_text())
            self.assertEqual(profiles['Profiles'][0]['Name'], 'Codex')
            self.assertIn('codex-launch.sh', profiles['Profiles'][0]['Command'])
            for path, text in installer.build_plan(home).items():
                self.assertEqual(path.read_text(), text)

    def test_claude_registration_preserves_model_and_other_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.fixture(home)
            (home / '.claude').mkdir()
            other = {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'memory-hook'}]}
            (home / '.claude/settings.json').write_text(json.dumps({'model': 'keep', 'hooks': {'PreToolUse': [other]}}))
            data = json.loads(installer.build_plan(home)[home / '.claude/settings.json'])
            self.assertEqual(data['model'], 'keep')
            self.assertIn(other, data['hooks']['PreToolUse'])
            self.assertEqual(len(data['hooks']['PreToolUse']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
