# Repository instructions

This is a chezmoi source repository for macOS dotfiles, primarily using fish
and Homebrew at `/opt/homebrew`. It is used on both personal and enterprise
managed Macs.

## Source layout and chezmoi

- Edit files in this repository. Apply changes to the live home directory or
  system only when the user requests it; `chezmoi apply` and `chezmoi update`
  also run scripts that install packages and change system settings.
- Preserve chezmoi naming conventions: `dot_` becomes `.`, `private_` controls
  permissions, `executable_` marks executable files, and `.tmpl` files are Go
  templates.
- Keep repository-only files in `.chezmoiignore`, including this file, tests,
  and `Brewfile`. `Brewfile` is read directly from the source directory.
- Preserve `before`/`after` script phases and numeric ordering within them.
  Bootstrap scripts must tolerate repeat runs and partial installations.
- `run_onchange` scripts rerun when their rendered contents change. Preserve
  the embedded hashes of `Brewfile` and fish plugin lists in the templates.
- `.chezmoi.toml.tmpl` generates chezmoi's config during initialization; after
  changing it, tell the user to rerun `chezmoi init` to regenerate the config.

## Shell behavior and reliability

- Keep fish code in fish syntax. Scripts using `/bin/bash` must work with
  macOS's bundled Bash 3.2; use macOS-compatible command options.
- Quote paths and arguments, including paths with spaces. Preserve existing
  user configuration when bootstrapping applications.
- In `run_onchange_after_40-macos-defaults.sh`, preference writes are
  best-effort: report individual failures, attempt the remaining writes, and
  exit successfully. Enterprise restrictions must not block chezmoi here.
- Installation failures must remain visible and return a nonzero status so
  chezmoi can retry. Do not extend preference error handling to installers.
- `dot_local/bin/executable_update.fish` attempts all update steps, reports
  each result, and returns failure if a required step fails. Preserve this
  behavior and check pipeline statuses when parsing command output.
- Keep credentials, tokens, and machine-specific secrets out of tracked files.

## Verification

- Choose checks that match the change. Use `bash -n` for plain Bash scripts
  and `fish --no-config --no-execute` for fish files. Render `.tmpl` files
  before checking their shell syntax.
- For behavior changes, use relevant tests under `tests/`. The full offline
  suite is `python3 -B -m unittest discover -s tests -v`; fish tests require
  fish, and some tests also require Git or ripgrep. Report skipped checks.
- Use temporary homes and command stubs for verification that would otherwise
  install packages, restart services, or change preferences. Existing tests
  follow this pattern.
- Check `git diff --check` and review the diff. Documentation-only changes do
  not require the full test suite.
