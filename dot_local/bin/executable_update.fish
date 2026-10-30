#!/usr/bin/env fish
# Update everything: dotfiles, Homebrew, nvim plugins, fish plugins, global packages, macOS.
# Steps keep going when one fails, so a single broken tool doesn't block the rest.
# --local runs only ~/.config/fish/update.local.fish, with the same logging and summary.

argparse --max-args=0 local -- $argv
or exit 2

function colorize_text
    echo ""
    set_color --bold green
    echo $argv
    set_color normal
end

set -g __update_results
set -g __update_failed 0

function update_step --argument-names label
    set -l step_log (mktemp -t update.XXXXXX)
    or begin
        set -ga __update_results "$label: FAILED (could not create log)"
        set -g __update_failed 1
        return 1
    end
    # Keep diagnostics even when a later updater redraws the terminal.
    $argv[2..-1] 2>&1 | tee "$step_log"
    set -l step_status $pipestatus
    if test $step_status[1] -eq 0
        set step_status $step_status[2]
    else
        set step_status $step_status[1]
    end
    if test $step_status -eq 0
        set -ga __update_results "$label: OK"
        rm -f "$step_log"
    else
        set -ga __update_results "$label: FAILED (exit $step_status) — log: $step_log"
        set -g __update_failed 1
    end
    return $step_status
end

function update_npm_globals
    # --parseable fields: path:name@wanted:name@current:name@latest:dependent
    set -l outdated (/opt/homebrew/bin/npm outdated -g --parseable | cut -d: -f4)
    set -l pipeline_status $pipestatus
    # npm returns 1 when it finds outdated packages; other failures must not
    # be hidden by cut succeeding or by an empty list of packages.
    if not contains -- $pipeline_status[1] 0 1
        echo "npm outdated failed (exit $pipeline_status[1])" >&2
        return $pipeline_status[1]
    end
    if test $pipeline_status[2] -ne 0
        echo "Parsing npm outdated failed (exit $pipeline_status[2])" >&2
        return $pipeline_status[2]
    end
    if test (count $outdated) -gt 0
        /opt/homebrew/bin/npm install -g $outdated
        return $status
    else if test $pipeline_status[1] -ne 0
        echo "npm outdated failed without a list of outdated packages" >&2
        return $pipeline_status[1]
    end
    echo "all global npm packages are up to date"
end

colorize_text '>>> start updating ...'
# sudo --validate

if not set -q _flag_local
    # first, so the later steps run with the freshly updated brew-installed tools
    colorize_text '>>> updating Homebrew'
    update_step 'brew tap --repair' brew tap --repair
    update_step 'brew update' brew update
    # --greedy-auto-updates also upgrades casks that normally update themselves
    update_step 'brew upgrade' brew upgrade --greedy-auto-updates --yes
    update_step 'brew cleanup' brew cleanup

    # pulls the dotfiles repo and applies it, which also runs the run_onchange install scripts
    colorize_text '>>> updating dotfiles'
    update_step 'chezmoi update' chezmoi update

    colorize_text '>>> syncing atuin history'
    update_step 'atuin sync' atuin sync

    colorize_text '>>> updating neovim plugins'
    update_step 'neovim plugins' nvim --headless "+Lazy! sync" "+UpdateRemotePlugins" +qa

    colorize_text '>>> updating fish plugins and completions'
    update_step 'fisher update' fisher update
    update_step 'fish completions' fish_update_completions

    # brew's npm, the same node that run_onchange_after_30-install-npm-globals.sh installs into
    colorize_text '>>> updating npm'
    update_step 'npm self-update' /opt/homebrew/bin/npm install -g npm@latest
    colorize_text '>>> updating global npm packages'
    # install only what's outdated: `npm update -g` also re-fetches git-installed packages like
    # git-iadd from the registry, where its tarball is gone (404), and that aborts the whole update.
    update_step 'global npm packages' update_npm_globals

    if type -q uv
        colorize_text '>>> updating uv tools'
        update_step 'uv tool upgrade' uv tool upgrade --all
    else
        set -ga __update_results 'uv: SKIPPED (not installed)'
    end

    if type -q rustup
        colorize_text '>>> updating rustup'
        update_step 'rustup update' rustup update
    else
        set -ga __update_results 'rustup: SKIPPED (not installed)'
    end

    if test -n "$SKIP_SOFTWAREUPDATE"; and test "$SKIP_SOFTWAREUPDATE" != 0
        set -ga __update_results 'Apple updates: SKIPPED (SKIP_SOFTWAREUPDATE set)'
    else
        colorize_text '>>> checking Apple updates'
        update_step 'Apple updates' /usr/sbin/softwareupdate --all --install --force
    end
end

if test -f "$HOME/.config/fish/update.local.fish"
    colorize_text '>>> running local updates'
    function update_local
        source "$HOME/.config/fish/update.local.fish"
    end
    update_step 'local updates' update_local
else if set -q _flag_local
    set -ga __update_results 'local updates: SKIPPED (not configured)'
end

colorize_text '>>> update summary'
for result in $__update_results
    switch $result
        case '*: OK'
            set_color green
        case '*: FAILED*'
            set_color red
        case '*'
            set_color yellow
    end
    echo $result
    set_color normal
end
exit $__update_failed
