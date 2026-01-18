#!/bin/bash
# work-statusline.sh - Custom status line for Claude Code workers
#
# Shows: #<issue> → PR #<pr> | <stage> | <context_bar> <percent>%
# Falls back to git branch/status when not in a worker session.
#
# Requires: jq, sqlite3, Nerd Font (for icons)

set -euo pipefail

# Read status line input from Claude Code
INPUT=$(cat)

# Database path
DB_PATH="${WORK_DB_PATH:-$HOME/.worktrees/work-sessions.db}"

# =============================================================================
# Context Bar Rendering
# =============================================================================

render_context_bar() {
    local pct="${1:-0}"
    local bar_width=8

    # Calculate filled/empty blocks
    local filled=$((pct * bar_width / 100))
    local empty=$((bar_width - filled))

    # Color based on usage (ANSI escape codes)
    local color
    if (( pct <= 50 )); then
        color="\033[32m"  # Green
    elif (( pct <= 75 )); then
        color="\033[33m"  # Yellow
    elif (( pct <= 90 )); then
        color="\033[38;5;208m"  # Orange
    else
        color="\033[31m"  # Red
    fi
    local reset="\033[0m"

    # Build bar
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done

    echo -e "${color}${bar}${reset} ${pct}%"
}

# =============================================================================
# Worker Status Line
# =============================================================================

render_worker_status() {
    local worker_id="$1"
    local context_pct="${2:-0}"

    # Query worker info from database
    if [[ ! -f "$DB_PATH" ]]; then
        return 1
    fi

    local worker_info
    worker_info=$(sqlite3 -separator '|' "$DB_PATH" "
        SELECT COALESCE(jira_key, CAST(issue_number AS TEXT), '?'),
               COALESCE(pr_number, 0),
               COALESCE(stage, 'unknown')
        FROM workers
        WHERE id = $worker_id
        LIMIT 1
    " 2>/dev/null) || return 1

    if [[ -z "$worker_info" ]]; then
        return 1
    fi

    # Parse fields
    local issue pr_num stage
    IFS='|' read -r issue pr_num stage <<< "$worker_info"

    # Build status line
    local status="#${issue}"

    if [[ "$pr_num" != "0" && -n "$pr_num" ]]; then
        status+=" → PR #${pr_num}"
    fi

    status+=" | ${stage} | $(render_context_bar "$context_pct")"

    echo -e "$status"
}

# =============================================================================
# Fallback Status Line (non-worker)
# =============================================================================

render_fallback_status() {
    local context_pct="${1:-0}"

    # Get git branch
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || branch=""

    # Get git status indicators
    local git_status=""
    if [[ -n "$branch" ]]; then
        # Check for uncommitted changes
        if ! git diff --quiet 2>/dev/null; then
            git_status+="*"
        fi
        # Check for staged changes
        if ! git diff --cached --quiet 2>/dev/null; then
            git_status+="+"
        fi
        # Check for untracked files
        if [[ -n $(git ls-files --others --exclude-standard 2>/dev/null | head -1) ]]; then
            git_status+="?"
        fi
    fi

    # Build status line
    local status=""
    if [[ -n "$branch" ]]; then
        status=" ${branch}"
        if [[ -n "$git_status" ]]; then
            status+=" [${git_status}]"
        fi
        status+=" | $(render_context_bar "$context_pct")"
    else
        status="$(render_context_bar "$context_pct")"
    fi

    echo -e "$status"
}

# =============================================================================
# Main
# =============================================================================

# Extract context percentage from Claude Code input (2.1.6+)
CONTEXT_PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // 0' 2>/dev/null || echo "0")
# Convert to integer
CONTEXT_PCT=${CONTEXT_PCT%.*}

# Check if we're in a worker session
if [[ -n "${WORK_WORKER_ID:-}" ]]; then
    if render_worker_status "$WORK_WORKER_ID" "$CONTEXT_PCT"; then
        exit 0
    fi
fi

# Fallback to git status
render_fallback_status "$CONTEXT_PCT"
