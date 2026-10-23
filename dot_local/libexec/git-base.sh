# Print the branch the current one forked from, for git base, git dm and git dmr.
# Candidates are the start point in the branch's reflog, origin's default branch, main,
# master, develop and dev, each as origin's copy and the local branch. The one with the
# nearest merge base wins and earlier candidates win ties, so a stale local main loses
# to origin/main and an unpushed local parent beats its origin copy.

current=$(git symbolic-ref -q --short HEAD)
start=
if [ -n "$current" ]; then
    start=$(git reflog show --format=%gs "refs/heads/$current" -- 2>/dev/null |
        sed -n 's/^branch: Created from //p' | tail -n 1)
    # created from the checkout: the start point is the branch left by its oldest checkout
    if [ "$start" = HEAD ]; then
        start=$(git reflog show --format=%gs HEAD -- 2>/dev/null | awk -v to=" to $current" '
            index($0, "checkout: moving from ") == 1 && substr($0, length($0) - length(to) + 1) == to {
                from = substr($0, 23, length($0) - 22 - length(to))
            }
            END { print from }')
    fi
fi

best=
best_count=
for name in "$start" "$(git symbolic-ref -q --short refs/remotes/origin/HEAD)" main master develop dev; do
    [ -n "$name" ] || continue
    for ref in "origin/$name" "$name"; do
        case $ref in "$current" | "origin/$current") continue ;; esac
        git rev-parse -q --verify "$ref^{commit}" >/dev/null || continue
        count=$(git rev-list --count "$ref..HEAD") || exit
        if [ -z "$best" ] || [ "$count" -lt "$best_count" ]; then
            best=$ref
            best_count=$count
        fi
    done
done

if [ -z "$best" ]; then
    echo "git base: no start point, main, master, develop or dev branch to compare with" >&2
    exit 1
fi
printf '%s\n' "$best"
