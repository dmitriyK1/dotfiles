function fix-clipboard --description "Reset Universal Clipboard"
    echo "Restarting sharingd, pboard & bluetoothd..."
    defaults write com.apple.sharingd DisallowHandoff -bool false

    # Restart user-level processes
    killall sharingd pboard 2>/dev/null

    # Restart system-level Bluetooth daemon (requires password)
    sudo killall bluetoothd 2>/dev/null

    echo "✓ Universal Clipboard reset completed!"
end
