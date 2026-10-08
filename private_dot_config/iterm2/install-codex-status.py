#!/usr/bin/python3
"""Install local iTerm hooks and remove iterm2-status@personal.

Run manually after deploying the scripts, or use the chezmoi after script:
  /usr/bin/python3 ~/.config/iterm2/install-codex-status.py
Use --dry-run to inspect the migration. New hooks need trust via /hooks.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import os

EVENTS = (
    'SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PermissionRequest',
    'PostToolUse', 'PreCompact', 'PostCompact', 'SubagentStart',
    'SubagentStop', 'Stop', 'Interrupt', 'SessionEnd',
)
SELECTOR = 'iterm2-status@personal'
OWNED_GUIDS = {'CODEX-ITERM2-DEFAULT-0001', 'CODEX-ITERM2-WORKSPACE-0001',
               'TREY-CODEX-AGENT-0001', 'TREY-CODEX-ABILITIE-0001'}


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def remove_old_config(text):
    # Remove only this plugin's table and its hook trust entries. Preserve all
    # other settings byte for byte, including unrelated hooks and plugins.
    blocks = re.split(r'(?m)(?=^\[)', text)
    return ''.join(block for block in blocks if not (
        block.startswith('[plugins."' + SELECTOR + '"]') or
        block.startswith('[hooks.state."' + SELECTOR + ':')
    ))


def build_plan(home):
    config = home / '.codex/config.toml'
    hooks = home / '.codex/hooks.json'
    marketplace = home / '.agents/plugins/marketplace.json'
    profiles = home / 'Library/Application Support/iTerm2/DynamicProfiles/codex-profiles.json'
    script = home / '.config/iterm2/codex-status.py'
    launcher = home / '.config/iterm2/codex-launch.sh'
    if not script.is_file() or not launcher.is_file():
        raise RuntimeError('Local status script or launcher is missing.')
    hook_data = read_json(hooks, {})
    hook_data.setdefault('description', 'Local Codex lifecycle hooks')
    groups = hook_data.setdefault('hooks', {})
    command = '/usr/bin/python3 ' + shlex.quote(str(script))
    for event in EVENTS:
        existing = groups.setdefault(event, [])
        if not any(handler.get('command') == command
                   for group in existing for handler in group.get('hooks', [])):
            existing.append({'hooks': [{'type': 'command', 'command': command, 'timeout': 3}]})
    plan = {hooks: json.dumps(hook_data, indent=2) + '\n'}
    if config.exists():
        plan[config] = remove_old_config(config.read_text())
    if marketplace.exists():
        data = read_json(marketplace, {})
        data['plugins'] = [p for p in data.get('plugins', []) if p.get('name') != 'iterm2-status']
        plan[marketplace] = json.dumps(data, indent=2) + '\n'
    claude = home / '.claude/settings.json'
    claude_data = read_json(claude, {})
    claude_groups = claude_data.setdefault('hooks', {})
    claude_command = shlex.quote(str(home / '.config/iterm2/cc-status'))
    for event in ('Notification', 'PermissionRequest', 'PostToolUse', 'PreToolUse',
                  'SessionEnd', 'SessionStart', 'Stop', 'StopFailure', 'SubagentStop', 'UserPromptSubmit'):
        existing = claude_groups.setdefault(event, [])
        if not any(handler.get('command') == claude_command
                   for group in existing for handler in group.get('hooks', [])):
            existing.append({'hooks': [{'type': 'command', 'command': claude_command}]})
    plan[claude] = json.dumps(claude_data, indent=2) + '\n'
    if not profiles.exists():
        profile = {'Guid': 'CODEX-ITERM2-DEFAULT-0001', 'Name': 'Codex',
                   'Dynamic Profile Parent Name': 'Default', 'Tags': ['ai', 'codex', 'local-hooks'],
                   'Custom Command': 'Yes', 'Custom Directory': 'Recycle',
                   'Command': '/opt/homebrew/bin/fish -lic ' + shlex.quote('/bin/sh ' + shlex.quote(str(launcher)))}
        plan[profiles] = json.dumps({'Profiles': [profile]}, indent=2) + '\n'
    else:
        data = read_json(profiles, {})
        for profile in data.get('Profiles', []):
            if profile.get('Guid') in OWNED_GUIDS:
                # Preserve appearance and identity; detach only the launcher.
                command = '/bin/sh ' + shlex.quote(str(launcher))
                profile['Command'] = '/opt/homebrew/bin/fish -lic ' + shlex.quote(command)
                profile['Tags'] = [t for t in profile.get('Tags', []) if t != 'iterm2-status']
                if 'local-hooks' not in profile['Tags']:
                    profile['Tags'].append('local-hooks')
        plan[profiles] = json.dumps(data, indent=2) + '\n'
    return plan


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    permissions = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix='.codex-status-', dir=str(path.parent))
    try:
        os.fchmod(fd, permissions)
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(home, dry_run=False, run=subprocess.run):
    plan = build_plan(home)
    for path in plan:
        print('Update:', path)
    print('Remove plugin:', SELECTOR)
    print('Archive old runtime: ~/.config/codex-iterm2-status')
    if dry_run:
        return
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('codex is not on PATH; run this from your normal terminal.')
    # Resolve installation before touching any files. Codex removal writes its
    # config, so read the cleaned config again after that command succeeds.
    installed = False
    if (home / '.agents/plugins/marketplace.json').exists():
        result = run([codex, 'plugin', 'list', '--marketplace', 'personal', '--json'],
                     check=True, capture_output=True, text=True, timeout=30)
        installed = any(p.get('pluginId') == SELECTOR for p in json.loads(result.stdout).get('installed', []))
    backup = home / '.config/iterm2/backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True, mode=0o700)
    originals = {path: path.read_bytes() if path.exists() else None for path in plan}
    for i, (path, content) in enumerate(originals.items()):
        if content is not None:
            (backup / ('{}-{}'.format(i, path.name))).write_bytes(content)
    (backup / 'manifest.json').write_text(json.dumps({str(path):
        '{}-{}'.format(i, path.name) if content is not None else None
        for i, (path, content) in enumerate(originals.items())}, indent=2) + '\n')
    print('Backup:', backup)
    # Register first, so a failed plugin uninstall leaves the old integration
    # working and the replacement available for review.
    hooks_path = home / '.codex/hooks.json'
    atomic_write(hooks_path, plan[hooks_path])
    if installed:
        run([codex, 'plugin', 'remove', SELECTOR, '--json'], check=True, timeout=30)
    config_path = home / '.codex/config.toml'
    if config_path.exists():
        plan[config_path] = remove_old_config(config_path.read_text())
    for path, content in plan.items():
        if path != hooks_path:
            atomic_write(path, content)
    runtime = home / '.config/codex-iterm2-status'
    if runtime.exists():
        shutil.move(str(runtime), str(backup / 'old-runtime'))
    print('Installed 12 local hooks; removed the old plugin and marketplace entry.')
    print('Restart Codex in iTerm, then open /hooks and trust the new hooks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        install(Path.home(), args.dry_run)
    except Exception as exc:
        parser.exit(1, 'Migration stopped: {}\n'.format(exc))
