#!/bin/bash
# Install global npm packages into Homebrew's node; re-runs whenever this list changes.
set -euo pipefail

# brew's npm, so packages don't land inside whichever nvm node version is active
eval "$(/opt/homebrew/bin/brew shellenv)"

packages=(
  ntl
  recursive-blame
  github:ruyadorno/git-iadd # npm registry tarball is gone (404)
)
# npm 12 refuses git specs by default (allow-git=none); root allows only the ones listed here
npm install -g --allow-git=root "${packages[@]}"
