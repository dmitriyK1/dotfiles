function toggle-sleep --description "Toggle system sleep (incl. lid-close sleep)"
    set -l power_settings (command pmset -g); or return
    # a missing SleepDisabled line in pmset -g counts as sleep enabled
    if string match -qr '^\s*SleepDisabled\s+1' -- $power_settings
        command sudo pmset -a disablesleep 0; or return
        echo "✓ Sleep enabled"
    else
        command sudo pmset -a disablesleep 1; or return
        echo "✓ Sleep disabled"
    end
end
