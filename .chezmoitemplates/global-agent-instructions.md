# Global Agent Instructions

## Working approach

- Be concise and direct. Explain decisions when they affect correctness, scope,
  or meaningful tradeoffs.
- Follow project-specific instructions and established repository conventions.
  More specific project guidance overrides these defaults.
- Investigate the root cause and make the smallest robust fix. Keep changes
  focused on the requested task and preserve existing user changes.
- Carry authorized work through inspection, implementation, and verification
  without asking for confirmation on routine, reversible intermediate steps.
  Ask when a missing decision materially affects scope or the next action
  requires authorization.

## Code quality

- Follow the project's typing and coding conventions. Keep functions focused
  and introduce abstractions when they simplify the requested change.
- Preserve useful documentation, comments, and tests; update them when behavior
  changes. Do not remove or weaken tests merely to hide failures.
- Keep real credentials out of output and tracked files. Use placeholders in
  examples and handle sensitive configuration only as needed for the task.

## Tools and execution

- Prefer `rg` for text search and `rg --files` or `fd` for file discovery.
- Keep searches and output focused. Search dependencies, generated files, and
  hidden files when the task requires them.
- Use `ast-grep` when structural matching makes code search or rewriting safer.
- Prefer targeted patches for code edits; use `sd` for straightforward text
  replacements. Inspect matches before broad replacements and review the diff.
- Use `jq` or `yq` to extract relevant structured data and keep output bounded.
- Use `eza` for directory overviews and `tokei` for language statistics when
  those help the task; neither is a required startup step.
- Use preferred tools when available and appropriate. Fall back to available
  alternatives when needed.
- Run CLI commands non-interactively with explicit arguments. Avoid commands
  that wait for terminal prompts or open text editors.

## Verification

- Run the project checks relevant to the change using the repository's
  established commands. Scale verification to the scope and risk of the change.
- Fix regressions caused by the change. Report pre-existing failures and
  environment limitations separately rather than expanding scope silently.
- Use ShellCheck when modifying shell scripts it supports.
- Inspect the final diff for unintended changes.
- Report what was verified, any failures, and checks that could not run.

## Git

- Commit and push when requested or authorized by the established workflow.
  When committing, keep commits focused and descriptions clear.
- Do not discard user changes or rewrite shared history without explicit
  authorization.
