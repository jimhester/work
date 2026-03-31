#!/bin/bash
# work-worktree-create.sh - WorktreeCreate hook for Claude Code
#
# Creates git worktrees in ~/.worktrees/{repo}/{name} using work's conventions,
# so that CC's isolation: "worktree" subagents and EnterWorktree tool share the
# same worktree root as `work` workers.
#
# Input (stdin JSON): { hook_event_name: "WorktreeCreate", name: <slug>, cwd, session_id, ... }
# Output (stdout):    the absolute path to the created (or existing) worktree

set -euo pipefail

HOOK_INPUT=$(cat)
NAME=$(echo "$HOOK_INPUT" | jq -r '.name')
CWD=$(echo "$HOOK_INPUT" | jq -r '.cwd')

WORKTREE_BASE="${WORKTREE_BASE:-$HOME/.worktrees}"

# Get the main repo root, even when CWD is already inside a worktree.
# --git-common-dir always points to the main .git directory.
REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || {
    echo "work-worktree-create: not in a git repository" >&2
    exit 1
}
GIT_COMMON=$(git -C "$CWD" rev-parse --git-common-dir 2>/dev/null)
[[ "$GIT_COMMON" != /* ]] && GIT_COMMON="$REPO_ROOT/$GIT_COMMON"
MAIN_REPO_ROOT=$(dirname "$GIT_COMMON")
REPO_NAME=$(basename "$MAIN_REPO_ROOT")

# Sanitize name for use as path and branch components (/ -> -)
SAFE_NAME="${NAME//\//-}"
BRANCH_NAME="worktree-${SAFE_NAME}"
WORKTREE_PATH="$WORKTREE_BASE/$REPO_NAME/$SAFE_NAME"

# If the worktree is already registered at this path, just return it
if git -C "$MAIN_REPO_ROOT" worktree list --porcelain 2>/dev/null | grep -q "^worktree $WORKTREE_PATH$"; then
    echo "$WORKTREE_PATH"
    exit 0
fi

mkdir -p "$(dirname "$WORKTREE_PATH")"

# Try to create with a new branch; fall back to attaching existing branch
if ! git -C "$MAIN_REPO_ROOT" worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH" HEAD 2>/dev/null; then
    git -C "$MAIN_REPO_ROOT" worktree add "$WORKTREE_PATH" "$BRANCH_NAME" 2>/dev/null || {
        echo "work-worktree-create: failed to create worktree at $WORKTREE_PATH" >&2
        exit 1
    }
fi

# Symlink claude.local.md from the main repo if it exists, so local Claude
# instructions are available inside the worktree without being committed.
CLAUDE_LOCAL="$MAIN_REPO_ROOT/claude.local.md"
if [[ -f "$CLAUDE_LOCAL" ]]; then
    ln -sf "$CLAUDE_LOCAL" "$WORKTREE_PATH/claude.local.md" 2>/dev/null || true
fi

echo "$WORKTREE_PATH"
