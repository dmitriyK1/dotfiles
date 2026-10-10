"""Add fuzzy matching when a zoxide query finds nothing.

Preserve native matches, frecency ordering, filters, scores, and diagnostics.
Match the final keyword as an ordered subsequence of the directory name, or
approximately with autojump's 0.6 similarity threshold. Earlier keywords still
have to appear in the path, in order. Interactive queries remain native.
"""

import argparse
from difflib import SequenceMatcher
import os
import subprocess
import sys

ZOXIDE = "/opt/homebrew/bin/zoxide"
NO_MATCH = (b"zoxide: no match found\n", b"zoxide: you are already in the only match\n")


class QueryParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def query_options(arguments):
    parser = QueryParser(add_help=False, allow_abbrev=False)
    for short, long in (("a", "all"), ("i", "interactive"), ("l", "list"), ("s", "score")):
        parser.add_argument(f"-{short}", f"--{long}", action="store_true")
    parser.add_argument("--exclude")
    parser.add_argument("--base-dir")
    parser.add_argument("keywords", nargs="*")
    try:
        options, unknown = parser.parse_known_args(arguments)
    except ValueError:
        return None
    if unknown or options.interactive or not options.keywords:
        return None
    # Explicit path queries retain zoxide's path-component rules.
    if "/" in options.keywords[-1] or not options.keywords[-1]:
        return None
    return options


def approximate_match(path, keywords):
    folded = path.casefold()
    position = 0
    for keyword in keywords[:-1]:
        keyword = keyword.casefold()
        found = folded.find(keyword, position)
        if found < 0:
            return False
        position = found + len(keyword)
    basename = os.path.basename(path).casefold()
    # Earlier terms can consume part of the basename; match its remaining suffix.
    if position > len(folded) - len(basename):
        basename = folded[position:]
    keyword = keywords[-1].casefold()
    remaining = iter(basename)
    if all(character in remaining for character in keyword):
        return True
    matcher = SequenceMatcher(a=keyword, b=basename)
    return matcher.quick_ratio() >= 0.6 and matcher.ratio() >= 0.6


def write_result(result):
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


def main(arguments):
    options = query_options(arguments[1:])
    if options is None:
        os.execv(ZOXIDE, [ZOXIDE, *arguments])

    result = subprocess.run([ZOXIDE, *arguments], capture_output=True)
    if result.stdout or result.returncode not in (0, 1) or result.stderr not in (b"", *NO_MATCH):
        return write_result(result)

    candidates = [ZOXIDE, "query", "--list", "--score"]
    if options.all:
        candidates.append("--all")
    for flag, value in (("--exclude", options.exclude), ("--base-dir", options.base_dir)):
        if value is not None:
            candidates.extend((flag, value))
    listing = subprocess.run(candidates, capture_output=True)
    if listing.returncode:
        return write_result(listing)

    matches = []
    for line in listing.stdout.splitlines(keepends=True):
        fields = line.rstrip(b"\n").split(maxsplit=1)
        if len(fields) != 2:
            continue
        path = os.fsdecode(fields[1])
        if approximate_match(path, options.keywords):
            matches.append(line if options.score else fields[1] + b"\n")
            if not options.list:
                break
    if not matches:
        return write_result(result)
    sys.stdout.buffer.write(b"".join(matches))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except OSError as error:
        print(f"zoxide: {error}", file=sys.stderr)
        sys.exit(127 if isinstance(error, FileNotFoundError) else
                 126 if isinstance(error, PermissionError) else 1)
