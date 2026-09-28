function fix-clipboard --description "Reset macOS Universal Clipboard and sharingd"
    defaults write com.apple.sharingd DisallowHandoff -bool false
    killall sharingd pboard
end
