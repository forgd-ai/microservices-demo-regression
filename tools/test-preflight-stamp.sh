#!/usr/bin/env bash
# Verify the bundled preflight stamp-note.sh records the verdict in the
# lowercase form the enforcement hooks compare against. The orchestrator passes
# the display verdict (PASS/FAIL); the push hooks (check-preflight-note.sh,
# git-hooks/pre-push) only accept a stored verdict of "pass". If the stamp does
# not normalize, a genuine pass can never satisfy the gate.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARCHIVE="${REPO_ROOT}/tools/preflight.tar.gz"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}
require_cmd jq
require_cmd tar
require_cmd git

[[ -f "$ARCHIVE" ]] || {
  echo "archive not found: $ARCHIVE" >&2
  exit 1
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Extract the bundled plugin and run its stamp script inside a throwaway repo
# so the git note has a commit to attach to.
tar -xzf "$ARCHIVE" -C "$work"

repo="${work}/repo"
mkdir -p "$repo"
git -C "$repo" init -q
git -C "$repo" config user.email "test@example.com"
git -C "$repo" config user.name "preflight test"
# Don't inherit a developer's global commit.gpgsign=true; signing has no place
# in this throwaway repo and would fail non-interactively.
git -C "$repo" config commit.gpgsign false
git -C "$repo" commit -q --allow-empty -m "seed"

( cd "$repo" && bash "${work}/scripts/stamp-note.sh" PASS >/dev/null )

verdict="$(git -C "$repo" notes --ref=preflight show HEAD | jq -r '.verdict')"

if [[ "$verdict" != "pass" ]]; then
  echo "FAIL: stamp-note.sh stored verdict '${verdict}', expected 'pass'" >&2
  exit 1
fi

echo "PASS: stamp-note.sh normalizes the verdict to '${verdict}'"
