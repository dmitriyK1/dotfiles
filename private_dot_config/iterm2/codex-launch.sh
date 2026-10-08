#!/bin/sh
# Independent replacement for the old plugin's dynamic-profile launcher.
if [ "$TERM_PROGRAM" = "iTerm.app" ] && [ -n "$ITERM_SESSION_ID" ]; then
    printf '\033]21337;status=idle;indicator=#00d75f;status-color=#00d75f;detail=Codex\007'
fi
# Each terminal needs its own server environment. A shared daemon can retain
# ITERM_SESSION_ID from an earlier tab after that tab has disappeared.
if [ "$TERM_PROGRAM" = "iTerm.app" ] && [ -n "$ITERM_SESSION_ID" ]; then
    export CODEX_ITERM2_TAB="$ITERM_SESSION_ID"
fi
codex --no-daemon "$@"
codex_result=$?
if [ "$TERM_PROGRAM" = "iTerm.app" ] && [ -n "$ITERM_SESSION_ID" ]; then
    printf '\033]21337;status=;indicator=;status-color=;detail=\007'
fi
printf 'Codex exited (%s).\n' "$codex_result"
exec /opt/homebrew/bin/fish -l
