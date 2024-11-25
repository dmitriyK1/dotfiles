#!/bin/sh

# Ensure Homebrew is installed
if ! command -v brew &> /dev/null; then
  echo "Homebrew not found. Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Brewfile path
BREWFILE=$CHEZMOI_SOURCE_DIR/Brewfile

# Install packages from Brewfile
if [[ -f "$BREWFILE" ]]; then
  echo "Installing packages from Brewfile..."
  brew bundle --file="$BREWFILE"
else
  echo "Brewfile not found at $BREWFILE"
fi

if [ ! -d "$HOME/.config/nvim" ]; then
  git clone https://github.com/LazyVim/starter ~/.config/nvim
else
  echo "Directory ~/.config/nvim already exists. Aborting clone."
fi

