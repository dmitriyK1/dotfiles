#!/usr/bin/python3
"""Local Codex lifecycle hook for iTerm2's native Session Status.

Registered in ~/.codex/hooks.json. Uses only Python's standard library and
iTerm's bundled it2. Always returns {} and never changes tool permissions.
State contains lifecycle metadata, never prompts, commands or tool output.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager

EVENTS = (
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
    "PostToolUse", "PreCompact", "PostCompact", "SubagentStart",
    "SubagentStop", "Stop", "Interrupt", "SessionEnd",
)
COLORS = {"working": "#ff9500", "waiting": "#5f87ff", "idle": "#00d75f", "": ""}
TEXT_COLORS = dict(COLORS)


def terminal_id(value):
    candidate = value.rsplit(":", 1)[-1]
    return candidate.upper() if re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", candidate
    ) else None


def clean(value):
    return " ".join("".join(
        c for c in str(value or "") if not unicodedata.category(c).startswith("C")
    ).split())[:80]


def call_key(event):
    # PermissionRequest has no tool_use_id and can add a description. Match it
    # to PostToolUse by a digest of the stable input, without saving that input.
    payload = event.get("tool_input")
    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k != "description"}
        if event.get("tool_name") in {"Bash", "apply_patch"} and "command" in payload:
            payload = {"command": payload["command"]}
    raw = json.dumps([event.get("turn_id"), event.get("tool_name"), payload], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def transition(previous, event):
    name, sid = event.get("hook_event_name"), event.get("session_id")
    if name not in EVENTS or not isinstance(sid, str) or not sid:
        return None
    state = dict(previous)
    if state.get("session_id") != sid:
        # Child threads inherit the terminal environment. Only a new root
        # prompt can take over an occupied terminal; child events cannot.
        if state and name != "UserPromptSubmit":
            if not (state.get("closed") and name == "SessionStart"):
                return None
        elif not state and name not in {"SessionStart", "UserPromptSubmit"}:
            return None
        state = {"session_id": sid, "working": False, "agents": [], "pending": {}}
    if state.get("closed") and name not in {"SessionStart", "UserPromptSubmit"}:
        return None
    turn = event.get("turn_id")
    if turn and state.get("turn_id") and turn != state["turn_id"]:
        if name not in {"UserPromptSubmit", "SubagentStart", "SubagentStop", "SessionStart"}:
            return None
    state["pending"] = dict(state.get("pending", {}))
    state["agents"] = list(state.get("agents", []))
    state["project"] = clean(Path(event.get("cwd") or ".").name)
    state["closed"] = False
    if name == "SessionStart":
        if event.get("source") != "compact":
            state.update(working=False, agents=[], pending={}, turn_id=None)
    elif name == "UserPromptSubmit":
        state.update(working=True, pending={}, turn_id=turn)
    elif name in {"PreCompact", "PostCompact"}:
        # Preserve idle for a manual /compact; automatic compact keeps working.
        pass
    elif name == "PreToolUse":
        state["working"] = True
        tool = event.get("tool_name", "").split(".")[-1]
        if tool in {"request_user_input", "request_user_input_async"}:
            state["pending"][call_key(event)] = "Input needed"
    elif name == "PermissionRequest":
        state["pending"][call_key(event)] = "Approval needed"
    elif name == "PostToolUse":
        state["pending"].pop(call_key(event), None)
    elif name == "SubagentStart":
        agent = event.get("agent_id")
        if isinstance(agent, str) and agent not in state["agents"]:
            state["agents"].append(agent)
    elif name == "SubagentStop":
        agent = event.get("agent_id")
        if agent in state["agents"]:
            state["agents"].remove(agent)
    elif name == "Stop":
        state.update(working=False, pending={})
    elif name in {"Interrupt", "SessionEnd"}:
        state.update(working=False, pending={}, agents=[], closed=name == "SessionEnd")
    if state["closed"]:
        status, detail = "", ""
    elif state["pending"]:
        status, detail = "waiting", "Codex · " + next(iter(state["pending"].values()))
    else:
        status = "working" if state["working"] or state["agents"] else "idle"
        detail = "Codex · " + state["project"]
        if state["agents"]:
            detail += " · {} subagent(s)".format(len(state["agents"]))
    state.update(status=status, detail=detail, updated_at=time.time())
    return state


@contextmanager
def locked(path, timeout):
    with os.fdopen(os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600), "w") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("status lock busy")
                time.sleep(0.01)
        yield


def read_state(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".status-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def find_it2():
    candidate = (Path.home() / '.config/iterm2/cc-status').resolve().parent / 'it2'
    if not candidate.is_file():
        candidate = Path('/Applications/iTerm.app/Contents/Resources/utilities/it2')
    return candidate if candidate.is_file() else None


def report(event):
    data = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "codex-iterm-status"
    # A resumed conversation can retain the server's old terminal environment.
    # Explicit bindings name one thread and one terminal; never use active tab.
    target = read_state(data / 'targets.json').get(event.get('session_id'))
    explicit = terminal_id(os.environ.get('CODEX_ITERM2_TAB', ''))
    terminal = explicit or (terminal_id(target) if isinstance(target, str) else None)
    bound = bool(terminal)
    terminal = terminal or terminal_id(os.environ.get("ITERM_SESSION_ID", ""))
    if not terminal or (not bound and os.environ.get("TERM_PROGRAM") != "iTerm.app"):
        return
    it2 = find_it2()
    if not it2:
        return
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    path, lock = data / (terminal + ".json"), data / (terminal + ".lock")
    with locked(lock, 0.4):
        previous = read_state(path)
        state = transition(previous, event)
        if state is None:
            return
        state.update(revision=previous.get("revision", 0) + 1, reported=False)
        save_state(path, state)
    if explicit:
        # The local launcher supplies a fresh tab id even when resuming a
        # conversation whose former terminal has been closed.
        with locked(data / 'targets.lock', 0.1):
            targets = read_state(data / 'targets.json')
            targets[event['session_id']] = terminal
            save_state(data / 'targets.json', targets)
    # Serialize GUI writes separately from transitions, then send the latest
    # revision. A slow GUI must not lose a simultaneous approval/Stop event.
    deadline = time.monotonic() + 1.8
    with locked(data / (terminal + ".report.lock"), 0.8):
        while time.monotonic() < deadline:
            with locked(lock, 0.1):
                snapshot = read_state(path)
            if snapshot.get("reported"):
                return
            color = COLORS[snapshot["status"]]
            args = [str(it2), "session", "set-status", "--session", terminal,
                    "--status", snapshot["status"], "--dot-color", color,
                    "--text-color", TEXT_COLORS[snapshot["status"]], "--detail", snapshot["detail"],
                    "--background-tasks", str(len(snapshot["agents"]))]
            try:
                result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, timeout=1.2)
                ok = result.returncode == 0
                error = '' if ok else result.stderr.decode('utf-8', errors='replace')[:1000]
            except (OSError, subprocess.TimeoutExpired) as exc:
                ok = False
                error = str(exc)[:1000]
            with locked(lock, 0.1):
                latest = read_state(path)
                if latest.get("revision") == snapshot["revision"]:
                    latest["reported"] = ok
                    latest["last_error"] = error
                    save_state(path, latest)
                    return


def bind(session_id):
    """Run in the intended iTerm tab to bind a resumed conversation to it."""
    terminal = terminal_id(os.environ.get('ITERM_SESSION_ID', '') or
                           os.environ.get('TERM_SESSION_ID', ''))
    if os.environ.get('TERM_PROGRAM') != 'iTerm.app' or not terminal:
        raise RuntimeError('Run --bind from the intended iTerm tab.')
    data = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'codex-iterm-status'
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked(data / 'targets.lock', 0.4):
        targets = read_state(data / 'targets.json')
        targets[session_id] = terminal
        save_state(data / 'targets.json', targets)
    # Move the known lifecycle state with the conversation, so the very next
    # event can report even if SessionStart already ran before the binding.
    states = [read_state(p) for p in data.glob('*.json') if p.name != 'targets.json']
    states = [s for s in states if s.get('session_id') == session_id]
    if states:
        with locked(data / (terminal + '.lock'), 0.4):
            state = max(states, key=lambda s: s.get('updated_at', 0))
            state.update(reported=False, last_error='')
            save_state(data / (terminal + '.json'), state)
    report({'session_id': session_id, 'hook_event_name': 'SessionStart',
            'source': 'compact', 'cwd': os.getcwd()})
    status = read_state(data / (terminal + '.json'))
    print('Bound conversation {} to iTerm session {}'.format(session_id, terminal))
    print('Status delivered:', 'OK' if status.get('reported') else 'FAILED')
    if not status.get('reported'):
        print(status.get('last_error', 'No hook event was recorded.'))


def doctor():
    """Run from the actual iTerm tab to diagnose its environment and socket."""
    terminal = terminal_id(os.environ.get('ITERM_SESSION_ID', ''))
    print('TERM_PROGRAM:', os.environ.get('TERM_PROGRAM', '(missing)'))
    print('iTerm session:', terminal or '(missing or invalid)')
    it2 = Path.home() / '.config/iterm2/cc-status'
    it2 = it2.resolve().parent / 'it2'
    if not it2.is_file():
        it2 = Path('/Applications/iTerm.app/Contents/Resources/utilities/it2')
    try:
        result = subprocess.run([str(it2), 'session', 'list', '--json'],
                                capture_output=True, text=True, timeout=5)
        print('iTerm API:', 'OK' if result.returncode == 0 else 'FAILED')
        if result.returncode:
            print(result.stderr.strip())
        elif terminal:
            color = COLORS['idle']
            result = subprocess.run([str(it2), 'session', 'set-status', '--session', terminal,
                '--status', 'idle', '--dot-color', color, '--text-color', TEXT_COLORS['idle'],
                '--detail', 'Codex · connection test', '--background-tasks', '0'],
                capture_output=True, text=True, timeout=5)
            print('Test status:', 'OK' if result.returncode == 0 else 'FAILED')
            if result.returncode:
                print(result.stderr.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print('iTerm API:', str(exc))
    data = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'codex-iterm-status'
    if terminal:
        state = read_state(data / (terminal + '.json'))
        print('Last hook status:', state.get('status', '(no events)'))
        print('Last hook reported:', state.get('reported', '(no events)'))
        print('Last hook error:', state.get('last_error', '(not recorded yet)'))


def main():
    try:
        event = json.loads(sys.stdin.read(2 * 1024 * 1024))
        if isinstance(event, dict):
            report(event)
    except Exception:
        pass
    print("{}")


if __name__ == "__main__":
    if sys.argv[1:] == ['--doctor']:
        doctor()
    elif len(sys.argv) == 3 and sys.argv[1] == '--bind':
        bind(sys.argv[2])
    else:
        main()
