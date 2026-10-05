function toggle-sleep --description "Toggle system sleep (incl. lid-close sleep)"
    # a missing SleepDisabled line in pmset -g counts as sleep enabled
    if pmset -g | string match -qr '^\s*SleepDisabled\s+1'
        sudo pmset -a disablesleep 0; or return
        echo "✓ Sleep enabled"
    else
        sudo pmset -a disablesleep 1; or return
        echo "✓ Sleep disabled"
    end
end
