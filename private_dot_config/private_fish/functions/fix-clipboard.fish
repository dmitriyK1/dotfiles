function fix-clipboard --description "Restart Universal Clipboard services"
    set -l user_id (command id -ru); or return
    echo "Restarting sharingd, pboard & bluetoothd..."
    command defaults write com.apple.sharingd DisallowHandoff -bool false
    or begin
        set -l preference_status $status
        echo "fix-clipboard: could not update Handoff preference (status $preference_status)" >&2
        return $preference_status
    end

    # Match the caller's real UID, as killall does for user-level processes.
    for service in sharingd pboard
        command pgrep -U $user_id -x $service >/dev/null
        set -l lookup_status $status
        if test $lookup_status -eq 1
            echo "$service is not running; skipping."
            continue
        else if test $lookup_status -ne 0
            echo "fix-clipboard: could not check $service (status $lookup_status)" >&2
            return $lookup_status
        end

        command killall $service
        or begin
            set -l restart_status $status
            echo "fix-clipboard: could not restart $service (status $restart_status)" >&2
            return $restart_status
        end
    end

    # Restart system-level Bluetooth daemon (requires password)
    command sudo killall bluetoothd
    or begin
        set -l restart_status $status
        echo "fix-clipboard: could not restart bluetoothd (status $restart_status)" >&2
        return $restart_status
    end

    echo "✓ Restart signals sent. Try copying between your devices again."
end
