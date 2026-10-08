function codex --wraps codex --description 'Codex with status bound to this iTerm tab'
    if test "$TERM_PROGRAM" = iTerm.app; and set -q ITERM_SESSION_ID; and test -n "$ITERM_SESSION_ID"
        set -lx CODEX_ITERM2_TAB $ITERM_SESSION_ID
        if contains -- --no-daemon $argv
            command codex $argv
        else
            command codex --no-daemon $argv
        end
    else
        command codex $argv
    end
end
