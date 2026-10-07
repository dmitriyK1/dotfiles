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
copy_tmp=""
trap 'rm -rf "$starter_tmp"; if [ -n "$copy_tmp" ]; then rm -f "$copy_tmp"; fi' EXIT

git clone --depth=1 https://github.com/LazyVim/starter.git "$starter_tmp/repo"
# Export tracked files so the Neovim config doesn't become a nested Git repo.
mkdir "$starter_tmp/files"
git -C "$starter_tmp/repo" archive HEAD | tar -x -C "$starter_tmp/files"
test -f "$starter_tmp/files/init.lua"
test -f "$starter_tmp/files/lua/config/lazy.lua"
# Preserve files from an earlier, partial chezmoi setup.
# Copy only missing files: macOS cp -n returns failure when it skips a file.
copy_missing_file() {
  local starter_file="$1"
  local destination="$nvim_config/${starter_file#"$starter_tmp/files/"}"
  if [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
    mkdir -p "$(dirname "$destination")"
    # Publish only complete files so retries never preserve a truncated copy.
    copy_tmp="$(mktemp "$destination.XXXXXX")"
    cp -P "$starter_file" "$copy_tmp"
    mv "$copy_tmp" "$destination"
    copy_tmp=""
  fi
}

while IFS= read -r -d '' starter_file; do
  copy_missing_file "$starter_file"
done < <(find "$starter_tmp/files" \( -type f -o -type l \) ! -path "$starter_tmp/files/init.lua" -print0)

# Publish the entrypoint only after all supporting files are installed.
copy_missing_file "$starter_tmp/files/init.lua"
