#!/bin/sh

# Ensure Homebrew is installed
if ! command -v brew &> /dev/null; then
  echo "Homebrew not found. Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Brewfile path
BREWFILE="./Brewfile"

# Install packages from Brewfile
if [[ -f "$BREWFILE" ]]; then
  echo "Installing packages from Brewfile..."
  brew bundle --file="$BREWFILE"
else
  echo "Brewfile not found at $BREWFILE"
fi

git clone https://github.com/LazyVim/starter ~/.config/nvim
