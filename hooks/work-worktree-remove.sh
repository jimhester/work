#!/bin/bash
# work-worktree-remove.sh - WorktreeRemove hook for Claude Code
#
# Removes a git worktree and its branch when Claude Code (isolation: "worktree"
# subagents or ExitWorktree) is done with it.
#
# Input (stdin JSON): { hook_event_name: "WorktreeRemove", worktree_path: <path>, cwd, ... }

set -euo pipefail

HOOK_INPUT=$(cat)
WORKTREE_PATH=$(echo "$HOOK_INPUT" | jq -r '.worktree_path')
CWD=$(echo "$HOOK_INPUT" | jq -r '.cwd')

# Get the main repo root (handles being inside a worktree)
REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || REPO_ROOT="$CWD"
GIT_COMMON=$(git -C "$CWD" rev-parse --git-common-dir 2>/dev/null || echo ".git")
[[ "$GIT_COMMON" != /* ]] && GIT_COMMON="$REPO_ROOT/$GIT_COMMON"
MAIN_REPO_ROOT=$(dirname "$GIT_COMMON")

# Look up the branch before removing (so we can delete it too)
BRANCH=$(git -C "$MAIN_REPO_ROOT" worktree list --porcelain 2>/dev/null | \
    awk -v wp="$WORKTREE_PATH" '/^worktree /{cur=$2} /^branch / && cur==wp {print $2}' | \
    sed 's|refs/heads/||')

# Remove the worktree; fall back to rm -rf if git refuses (e.g. already gone)
git -C "$MAIN_REPO_ROOT" worktree remove --force "$WORKTREE_PATH" 2>/dev/null || \
    rm -rf "$WORKTREE_PATH"

# Prune any stale worktree metadata
git -C "$MAIN_REPO_ROOT" worktree prune 2>/dev/null || true

# Delete the branch if it follows our naming convention (worktree-*)
# so we don't accumulate stale local branches.
if [[ -n "$BRANCH" && "$BRANCH" == worktree-* ]]; then
    git -C "$MAIN_REPO_ROOT" branch -D "$BRANCH" 2>/dev/null || true
fi
