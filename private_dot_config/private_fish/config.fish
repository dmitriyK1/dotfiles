# colorizer:
# https://github.com/oh-my-fish/plugin-grc

# git flow completion:
# https://github.com/oh-my-fish/plugin-git-flow

# https://github.com/oh-my-fish/plugin-node-binpath
# https://github.com/oh-my-fish/plugin-brew

# fasd support here:
# https://github.com/fishgretel/fasd

# https://github.com/FabioAntunes/fish-nvm
# Run 'nvm_alias_command' to create aliases for binaries: npm node npx yarn

# fisher automatic install
if not functions -q fisher
    set -q XDG_CONFIG_HOME; or set XDG_CONFIG_HOME ~/.config
    curl https://git.io/fisher --create-dirs -sLo $XDG_CONFIG_HOME/fish/functions/fisher.fish
    fish -c fisher

    if test -f "$XDG_CONFIG_HOME/fish/fish_plugins"
        fisher install (cat $XDG_CONFIG_HOME/fish/fish_plugins)
    end
end

set -g theme_powerline_fonts no
set -g theme_nerd_fonts yes
set -g theme_display_node always
set -g theme_display_nvm yes
set fish_prompt_pwd_dir_length 1
# set -g theme_display_docker_machine yes
set -g fish_prompt_pwd_dir_length 0
set -g theme_display_jobs_verbose yes
set -g theme_show_exit_status yes
set -g theme_date_format "+%a %d-%m-%Y [%H:%M]"
# set -g fish_hybrid_key_bindings

if status --is-interactive
    # Commands to run in interactive sessions

    source ~/.config/fish/.fish_variables
    source ~/.config/fish/.fish_functions
    source ~/.config/fish/.fish_aliases
    [ -f $HOME/.config/fish/config.local.fish ]; and source $HOME/.config/fish/config.local.fish

    test -e {$HOME}/.iterm2_shell_integration.fish; and source {$HOME}/.iterm2_shell_integration.fish

    if command -v atuin >/dev/null
        atuin init fish | source
    end

    if command -v zoxide >/dev/null
        zoxide init fish | source
    end

    if command -v fzf >/dev/null
        fzf --fish | source
    end

    # caniuse --completion-fish | source

    # Generates shell code to override your shell's "command not found" handler with one that calls npx
    # source (npx --shell-auto-fallback fish | psub)

    function fish_user_key_bindings
        bind \cr _atuin_search
    end

    function tere
        set --local result (command tere $argv)
        [ -n "$result" ] && cd -- "$result"
    end

    # source (pyenv init -|psub)

    [ -f "$HOMEBREW_PREFIX/share/autojump/autojump.fish" ]; and source "$HOMEBREW_PREFIX/share/autojump/autojump.fish"

    #function fish_exit --on-event fish_exit
    #    atuin sync -f >/dev/null 2>&1
    #end
end

# activate https://github.com/adambrenecki/virtualfish
# eval (python3 -m virtualfish)

# You must call it on initialization or listening to directory switching won't work
# https://github.com/nvm-sh/nvm#deeper-shell-integration
#load_nvm

# vim: filetype=fish
