function spf --wraps spf --description 'Superfile, then cd to the last active panel'
    # Ask superfile for its state path so XDG overrides and macOS defaults both work.
    set -l lastdir (command spf pl --lastdir-file); or return $status
    # A previous interrupted run must not make help or a failed launch change directory.
    command rm -f -- "$lastdir"; or return $status

    command spf $argv
    set -l spf_status $status

    if test -f "$lastdir"
        if test $spf_status -eq 0
            source "$lastdir"
            set spf_status $status
        end
        command rm -f -- "$lastdir"
    end

    return $spf_status
end
