# colorizer:
# https://github.com/oh-my-fish/plugin-grc

# git flow completion:
# https://github.com/oh-my-fish/plugin-git-flow

# https://github.com/oh-my-fish/plugin-node-binpath
# https://github.com/oh-my-fish/plugin-brew

# fasd support here:
# https://github.com/fishgretel/fasd

set -g theme_powerline_fonts no
set -g theme_nerd_fonts yes
set -g theme_display_node always
set -g theme_display_nvm yes
# set -g theme_display_docker_machine yes
set -g fish_prompt_pwd_dir_length 0
set -g theme_display_jobs_verbose yes
set -g theme_show_exit_status yes
set -g theme_date_format "+%a %d-%m-%Y [%H:%M]"
# set -g fish_hybrid_key_bindings

source ~/.config/fish/.fish_variables

if status --is-interactive
    # Commands to run in interactive sessions

    source ~/.config/fish/.fish_functions

    # defining ~250 aliases takes ~30 ms per shell, so cache them as plain function definitions;
    # the cache is rebuilt whenever .fish_aliases or .fish_aliases.local changes
    set -l alias_file ~/.config/fish/.fish_aliases
    set -l alias_cache ~/.cache/fish/aliases.fish
    if not test -f $alias_cache; or test $alias_file -nt $alias_cache; or test $alias_file.local -nt $alias_cache
        mkdir -p ~/.cache/fish
        # alias-defined functions are the only ones whose --details is "-"
        fish --no-config -c 'source $argv[1]; for f in (functions --all --names); test "$(functions --details $f)" = "-"; and functions $f; end' $alias_file >$alias_cache.tmp
        and command mv $alias_cache.tmp $alias_cache
    end
    if test -f $alias_cache
        source $alias_cache
    else
        source $alias_file
    end

    [ -f $HOME/.config/fish/config.local.fish ]; and source $HOME/.config/fish/config.local.fish

    test -e {$HOME}/.iterm2_shell_integration.fish; and source {$HOME}/.iterm2_shell_integration.fish

    # Print the path of a cached copy of a tool's generated init script, so it isn't regenerated
    # on every start; rebuilt when the tool is upgraded (its resolved path changes) or the init
    # command changes. Sourced by the caller so the script runs at top level, not in this function
    function __cached_init
        set -l bin (command -s $argv[1]); or return
        set -l key "# "(path resolve $bin)" $argv"
        set -l cache ~/.cache/fish/init-$argv[1].fish
        set -l first
        if not test -f $cache; or not read first <$cache; or test "$first" != "$key"
            set -l out (command $argv); or return
            mkdir -p ~/.cache/fish
            printf '%s\n' $key $out >$cache
        end
        echo $cache
    end

    # fzf before atuin so atuin's ctrl-r binding wins over fzf-history-widget
    set -l init (__cached_init fzf --fish); and source $init
    set -l init (__cached_init atuin init fish); and source $init
    # zoxide only tracks directories for superfile's zoxide panel; autojump provides `j`
    set -l init (__cached_init zoxide init fish --no-cmd); and source $init
    functions -e __cached_init

    # caniuse --completion-fish | source

    # Generates shell code to override your shell's "command not found" handler with one that calls npx
    # source (npx --shell-auto-fallback fish | psub)

    # function tere
    #     set --local result (command tere --normal-search-anywhere --mouse=on $argv)
    #     [ -n "$result" ]; and cd -- "$result"
    # end

    # source (pyenv init -|psub)

    [ -f "$HOMEBREW_PREFIX/share/autojump/autojump.fish" ]; and source "$HOMEBREW_PREFIX/share/autojump/autojump.fish"

    #function fish_exit --on-event fish_exit
    #    atuin sync -f >/dev/null 2>&1
    #end
end

# activate https://github.com/adambrenecki/virtualfish
# eval (python3 -m virtualfish)
