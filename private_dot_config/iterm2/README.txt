iTerm2 status integration for Codex and Claude Code

chezmoi apply deploys these scripts and registers hooks with the after script.
Registration merges existing Codex and Claude settings and makes backups.
The old iterm2-status@personal plugin is removed if it is installed.
On a fresh Mac the installer also creates the optional Codex iTerm profile.
Review and trust new Codex hooks with /hooks once after installation.

The fish codex function and the profile launcher use --no-daemon and pass
CODEX_ITERM2_TAB so resumed conversations follow their new terminal tab.
Claude uses iTerm's original cc-status with an idle-text color override.
idle is green, working is orange, waiting is blue.
iTerm owns the cc-status symlink and resets it on launch, so chezmoi leaves
it alone. Claude hooks run cc-status-green.py with that symlink as argument.

Diagnostics: /usr/bin/python3 ~/.config/iterm2/codex-status.py --doctor
Manual setup: /usr/bin/python3 ~/.config/iterm2/install-codex-status.py
Runtime state, terminal bindings, backups and hook trust stay outside Git.
