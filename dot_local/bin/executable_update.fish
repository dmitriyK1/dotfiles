#!/usr/bin/env fish
# Update everything: dotfiles, Homebrew, nvim plugins, fish plugins, global packages, macOS.
# Steps keep going when one fails, so a single broken tool doesn't block the rest.

function colorize_text
    echo ""
    set_color --bold green
    echo $argv
    set_color normal
end

colorize_text '>>> start updating ...'
sudo --validate

# pulls the dotfiles repo and applies it, which also runs the run_onchange install scripts
colorize_text '>>> updating dotfiles'
chezmoi update

colorize_text '>>> purging autojump database from non-existing paths'
autojump --purge

colorize_text '>>> updating Homebrew'
brew update
# --greedy also upgrades casks that normally update themselves
brew upgrade --greedy
brew cleanup
brew tap --repair

colorize_text '>>> updating neovim plugins'
nvim --headless "+Lazy! sync" "+UpdateRemotePlugins" +qa

colorize_text '>>> updating fish plugins and completions'
fisher update
fish_update_completions
omf update

# brew's npm, the same node that run_onchange_after_30-install-npm-globals.sh installs into
colorize_text '>>> updating global npm packages'
# install only what's outdated: `npm update -g` also re-fetches git-installed packages like
# git-iadd from the registry, where its tarball is gone (404), and that aborts the whole update.
# --parseable lines are path:wanted:current:latest:location
set -l outdated (/opt/homebrew/bin/npm outdated -g --parseable | cut -d: -f4)
if test (count $outdated) -gt 0
    /opt/homebrew/bin/npm install -g $outdated
else
    echo "all global npm packages are up to date"
end

if type -q uv
    colorize_text '>>> updating uv and uv tools'
    uv self update
    uv tool upgrade --all
end

if type -q rustup
    colorize_text '>>> updating rustup'
    rustup update
end

colorize_text '>>> checking Apple updates'
/usr/sbin/softwareupdate --all --install --force
