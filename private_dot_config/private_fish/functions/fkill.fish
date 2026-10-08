function fkill --description "Kill processes selected with fzf or listening on a port (fkill [-SIGNAL] [:port | query])"
    set -l signal -TERM
    if string match -qr -- '^-[A-Za-z0-9]+$' "$argv[1]"
        set signal $argv[1]
        set -e argv[1]
    end

    set -l pids
    if string match -qr -- '^:[0-9]+$' "$argv[1]"
        set -l port (string sub -s 2 -- $argv[1])
        set pids (command lsof -ti tcp:$port -sTCP:LISTEN)
        if test -z "$pids"
            echo "fkill: nothing is listening on port $port" >&2
            return 1
        end
    else
        # pid -> listening TCP ports, appended to each row so ":3000" matches in fzf
        set -l ports (command lsof -nP -iTCP -sTCP:LISTEN -Fpn 2>/dev/null | awk '/^p/ { pid = substr($0, 2) } /^n/ { port = $0; sub(/.*:/, "", port); print pid " :" port }')
        set -l lines (command ps -axo pid=,user=,%cpu=,%mem=,comm= | awk -v map=(string join ";" $ports | string collect) '
            BEGIN { n = split(map, entries, ";"); for (i = 1; i <= n; i++) { split(entries[i], kv, " "); if (!index(" " seen[kv[1]] " ", " " kv[2] " ")) seen[kv[1]] = seen[kv[1]] " " kv[2] } }
            { print $0 seen[$1] }
        ' | fzf --multi --query "$argv" --header "TAB: multi-select, ENTER: kill $signal")
        or return

        set pids (string trim -- $lines | string replace -r '\s.*' '')
    end

    kill $signal $pids
end
