#!/bin/bash
# macOS preferences (curated from the old configs/osx.sh); re-runs whenever this file changes.
# Preferences are best-effort: managed Macs may forbid individual writes.
# Warn on failures without blocking chezmoi; retry when this file changes.
set -uo pipefail

failed=0
write() {
  if ! defaults write "$@"; then
    echo "Warning: defaults write $* failed; continuing (the preference may be restricted)." >&2
    failed=$((failed + 1))
  fi
}

# Finder
write NSGlobalDomain AppleShowAllExtensions -bool true
write com.apple.finder ShowStatusBar -bool true
write com.apple.finder ShowPathbar -bool true
write com.apple.finder _FXSortFoldersFirst -bool true
# search the current folder by default
write com.apple.finder FXDefaultSearchScope -string "SCcf"
write com.apple.finder FXEnableExtensionChangeWarning -bool false
# list view in all Finder windows
write com.apple.finder FXPreferredViewStyle -string "Nlsv"
# empty the Trash without a confirmation dialog
write com.apple.finder WarnOnEmptyTrash -bool false
# no .DS_Store files on network or USB volumes
write com.apple.desktopservices DSDontWriteNetworkStores -bool true
write com.apple.desktopservices DSDontWriteUSBStores -bool true

# Keyboard; fast repeat with a longer initial delay so brief key holds do not duplicate letters
# (System Settings minimums are 2 and 15), applied after logging out
write NSGlobalDomain KeyRepeat -int 2
write NSGlobalDomain InitialKeyRepeat -int 25
# key repeat instead of the accent picker when holding a key
write NSGlobalDomain ApplePressAndHoldEnabled -bool false
write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false

# Dock
write com.apple.dock autohide -bool true
write com.apple.dock autohide-delay -float 0
# show and hide the Dock instantly instead of sliding it in
write com.apple.dock autohide-time-modifier -float 0
# don't bounce app icons while apps launch
write com.apple.dock launchanim -bool false
# keep Spaces in a fixed order instead of rearranging them by recent use
write com.apple.dock mru-spaces -bool false

# TextEdit: plain text documents
write com.apple.TextEdit RichText -int 0

# Activity Monitor: sort by CPU usage, highest first, and show CPU usage as the Dock icon
write com.apple.ActivityMonitor SortColumn -string "CPUUsage"
write com.apple.ActivityMonitor SortDirection -int 0
write com.apple.ActivityMonitor IconType -int 5

# restart the apps whose preferences changed; they may not be running
killall Finder Dock >/dev/null 2>&1 || true

if [ "$failed" -gt 0 ]; then
  echo "Warning: $failed macOS preference write(s) failed; chezmoi will continue." >&2
fi

exit 0
