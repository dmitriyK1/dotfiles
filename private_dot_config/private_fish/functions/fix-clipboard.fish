function fix-clipboard --description "Reset Universal Clipboard"
    echo "Restarting sharingd & pboard..."
    defaults write com.apple.sharingd DisallowHandoff -bool false
    killall sharingd pboard 2>/dev/null
    echo "✓ Universal Clipboard reset completed!"
end
