function che --description "Fuzzy search and edit chezmoi files"
    set -l chezmoi_dir (chezmoi source-path)
    set -l file (fd --type f --hidden --exclude .git . $chezmoi_dir | string replace "$chezmoi_dir/" "" | fzf --preview "bat --color=always $chezmoi_dir/{}")

    if test -n "$file"
        nvim "$chezmoi_dir/$file"
    end
end
