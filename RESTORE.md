# Restore local configuration on a new Mac

Chezmoi restores the shared dotfiles. Keep the optional local files below in a
private backup outside this repository. Review them for the new Mac before
restoring, or recreate them from their purpose below.

## Files to recover

- `~/.config/homebrew/Brewfile.local`: packages needed only on this Mac. Review
  personal apps and tools before restoring the list to an enterprise managed Mac.
- `~/.config/homebrew/install.local.sh`: native installers for local tools. Keep
  this Bash script non-interactive and safe to repeat. It runs after the shared
  and local Brewfiles.
- `~/.gitconfig.local`: Git identity, signing key reference, and local overrides.
  Check `user.name`, `user.email`, and `user.signingkey`; configure access to the
  corresponding signing key separately.
- `~/.config/fish/`: restore any `config.local.fish`, `.fish_aliases.local`, and
  `.fish_variables.local` overrides. Update paths, hostnames, and variables for
  the new machine.
- `~/.config/fish/update.local.fish`: local update steps. Review tool availability
  and paths before running updates.
- `~/.gitignore_global`: ignore rules for this machine. Restore or adjust them
  independently of the shared dotfiles.

## Restore order

1. Initialize chezmoi with this repository without `--apply`.
2. Restore or recreate the relevant files above before the first apply, so the
   package installer can find the local Brewfile and native installer.
3. Review `chezmoi diff`, then run `chezmoi apply`. Apply also runs package
   installers, login-shell setup, and macOS preference scripts; reviewing the
   file diff does not preview those scripts' effects.
4. If the first apply installed optional tools, open a new fish session and run
   `chezmoi apply` again to refresh instructions gated on tool availability.
5. Sign in to tools again as needed. Check Git identity, signing-key access, and
   local command paths before using the restored setup.
