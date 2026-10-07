#!/bin/bash
# Make Homebrew's fish the login shell; each step is skipped when already in place.
set -euo pipefail

fish=/opt/homebrew/bin/fish
# installed by run_onchange_before_10-install-packages.sh; failing here lets run_once retry next apply
if [ ! -x "$fish" ]; then
  echo "fish not found at $fish" >&2
  exit 1
fi

# chsh refuses shells that are not listed in /etc/shells
if ! grep -qxF "$fish" /etc/shells; then
  echo "Adding $fish to /etc/shells..."
  # start on a new line if the file lacks a trailing newline
  { if [ -n "$(tail -c1 /etc/shells)" ]; then echo; fi; echo "$fish"; } | sudo tee -a /etc/shells >/dev/null
fi

current="$(dscl . -read "/Users/$(id -un)" UserShell | awk '{print $2}')"
if [ "$current" != "$fish" ]; then
  echo "Changing login shell from ${current:-unknown} to $fish..."
  chsh -s "$fish"
fi
