#!/bin/bash
# Bootstrap the official LazyVim starter before chezmoi applies our overrides.
# Existing Neovim configurations with an entrypoint are already initialized.
set -euo pipefail

nvim_config="$HOME/.config/nvim"
if [ -e "$nvim_config/init.lua" ] || [ -L "$nvim_config/init.lua" ] ||
   [ -e "$nvim_config/init.vim" ] || [ -L "$nvim_config/init.vim" ]; then
  exit 0
fi

echo "Installing LazyVim starter..."
starter_tmp="$(mktemp -d)"
trap 'rm -rf "$starter_tmp"' EXIT

git clone --depth=1 https://github.com/LazyVim/starter.git "$starter_tmp/repo"
# Export tracked files so the Neovim config doesn't become a nested Git repo.
mkdir "$starter_tmp/files"
git -C "$starter_tmp/repo" archive HEAD | tar -x -C "$starter_tmp/files"
test -f "$starter_tmp/files/init.lua"
test -f "$starter_tmp/files/lua/config/lazy.lua"
# Preserve files from an earlier, partial chezmoi setup.
# Copy only missing files: macOS cp -n returns failure when it skips a file.
while IFS= read -r -d '' starter_file; do
  destination="$nvim_config/${starter_file#"$starter_tmp/files/"}"
  if [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
    mkdir -p "$(dirname "$destination")"
    cp -P "$starter_file" "$destination"
  fi
done < <(find "$starter_tmp/files" \( -type f -o -type l \) -print0)
