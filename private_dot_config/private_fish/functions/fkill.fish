function fkill --description "Kill processes selected with fzf"
    set -l signal -TERM
    if string match -qr -- '^-[A-Za-z0-9]+$' "$argv[1]"
        set signal $argv[1]
        set -e argv[1]
    end

    set -l lines (command ps -axo pid=,user=,%cpu=,%mem=,comm= | fzf --multi --query "$argv" --header "TAB: multi-select, ENTER: kill $signal")
    or return

    set -l pids (string trim -- $lines | string replace -r '\s.*' '')
    kill $signal $pids
end
