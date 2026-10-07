#!/bin/bash
# macOS preferences (curated from the old configs/osx.sh); re-runs whenever this file changes.
# Every write is attempted even if one fails; a failure makes the script exit non-zero so
# chezmoi runs it again on the next apply.
set -uo pipefail

failed=0
write() {
  if ! defaults write "$@"; then
    echo "defaults write $* failed" >&2
    failed=1
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
# no .DS_Store files on network or USB volumes
write com.apple.desktopservices DSDontWriteNetworkStores -bool true
write com.apple.desktopservices DSDontWriteUSBStores -bool true

# Keyboard; values below the System Settings minimum (2 and 15), applied after logging out
write NSGlobalDomain KeyRepeat -int 1
write NSGlobalDomain InitialKeyRepeat -int 10
# key repeat instead of the accent picker when holding a key
write NSGlobalDomain ApplePressAndHoldEnabled -bool false
write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false

# Dock
write com.apple.dock autohide -bool true
write com.apple.dock autohide-delay -float 0
# keep Spaces in a fixed order instead of rearranging them by recent use
write com.apple.dock mru-spaces -bool false

# TextEdit: plain text documents
write com.apple.TextEdit RichText -int 0

# restart the apps whose preferences changed; they may not be running
killall Finder Dock >/dev/null 2>&1 || true

exit $failed
