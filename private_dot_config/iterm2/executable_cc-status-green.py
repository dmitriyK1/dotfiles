#!/usr/bin/python3
"""Run iTerm's Claude hook, then make idle text match its green indicator."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

UTILITIES = Path('/Applications/iTerm.app/Contents/Resources/utilities')
FINISHED = {'completed', 'failed', 'cancelled', 'canceled', 'killed', 'stopped', 'done'}


def background_count(payload):
    value = payload.get('background_tasks')
    if isinstance(value, list):
        return sum(1 for task in value if not isinstance(task, dict) or
                   str(task.get('status', '')).lower() not in FINISHED)
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return None


def becomes_idle(payload, stored_count):
    # Match the native hook's idle decisions. SubagentStop updates a count but
    # deliberately leaves visible status alone, so it must not recolor text.
    event = payload.get('hook_event_name')
    if event in {'SessionStart', 'SessionEnd'}:
        return True
    if event == 'Stop':
        return (background_count(payload) or 0) == 0
    if event == 'StopFailure' or (event == 'Notification' and
                                payload.get('notification_type') == 'idle_prompt'):
        count = background_count(payload)
        return (stored_count() if count is None else count) == 0
    return False


def main():
    raw = sys.stdin.buffer.read()
    try:
        result = subprocess.run([str(UTILITIES / 'cc-status')], input=raw,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        if result.returncode != 0:
            return
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return
        terminal = (os.environ.get('TERM_SESSION_ID') or
                    os.environ.get('ITERM_SESSION_ID') or '').rsplit(':', 1)[-1]
        if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', terminal):
            return
        def stored_count():
            try:
                result = subprocess.run([str(UTILITIES / 'it2'), 'session',
                    'get-background-tasks', '--session', terminal], capture_output=True, timeout=1)
                return max(0, int(result.stdout)) if result.returncode == 0 else 0
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return 0
        if becomes_idle(payload, stored_count):
            subprocess.run([str(UTILITIES / 'it2'), 'session', 'set-status',
                '--session', terminal, '--text-color', '#00d75f'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


if __name__ == '__main__':
    main()
