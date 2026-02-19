#!/bin/bash
# work-statusline.sh - Custom status line for Claude Code workers
#
# Shows: ~/path (± branch [hash] !?+) | $0.12 | ████░░░░ 52%
# Worker: #issue → PR #pr | stage | $0.12 | ████░░░░ 52%
# Worktree: repo:branch (± branch [hash]) | $0.12 | ████░░░░ 52%
#
# Requires: jq, sqlite3

set -euo pipefail

# Read status line input from Claude Code
INPUT=$(cat)

# Database path
DB_PATH="${WORK_DB_PATH:-$HOME/.worktrees/work-sessions.db}"

# ANSI colors (matching brute.zsh-theme solarized palette)
C_BLUE="\033[38;5;26m"
C_MAGENTA="\033[38;5;161m"
C_GREEN="\033[38;5;64m"
C_YELLOW="\033[38;5;172m"
C_RED="\033[38;5;124m"
C_ORANGE="\033[38;5;208m"
C_GRAY="\033[38;5;239m"
C_RESET="\033[0m"

# =============================================================================
# Context Bar
# =============================================================================

render_context_bar() {
    local pct="${1:-0}"
    local bar_width=8
    local filled=$((pct * bar_width / 100))
    local empty=$((bar_width - filled))

    local color
    if (( pct <= 50 )); then color="$C_GREEN"
    elif (( pct <= 75 )); then color="$C_YELLOW"
    elif (( pct <= 90 )); then color="$C_ORANGE"
    else color="$C_RED"
    fi

    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done

    echo -ne "${color}${bar}${C_RESET} ${pct}%"
}

# =============================================================================
# Cost
# =============================================================================

render_cost() {
    local cost_usd="${1:-}"
    if [[ -z "$cost_usd" || "$cost_usd" == "null" || "$cost_usd" == "0" ]]; then
        return
    fi
    # Format to 2 decimal places
    printf '$%.2f' "$cost_usd"
}

# =============================================================================
# Directory (shortened like zsh %~ with worktree awareness)
# =============================================================================

render_dir() {
    local cwd="${1:-}"
    [[ -z "$cwd" ]] && return

    local worktree_base="$HOME/.worktrees"

    # Worktree: show repo:branch instead of full path
    if [[ "$cwd" == "$worktree_base"/* ]]; then
        local rel="${cwd#$worktree_base/}"
        # rel is like "repo-name/branch-name/sub/dir" or "repo-name/branch-name"
        local repo="${rel%%/*}"
        local rest="${rel#*/}"
        if [[ "$rest" == "$rel" ]]; then
            # No subdirectory, just repo name
            echo -ne "${C_BLUE}${repo}${C_RESET}"
        else
            local branch="${rest%%/*}"
            local subdir="${rest#*/}"
            if [[ "$subdir" == "$rest" || "$subdir" == "$branch" ]]; then
                echo -ne "${C_BLUE}${repo}${C_GRAY}:${C_MAGENTA}${branch}${C_RESET}"
            else
                echo -ne "${C_BLUE}${repo}${C_GRAY}:${C_MAGENTA}${branch}${C_GRAY}/${C_BLUE}${subdir}${C_RESET}"
            fi
        fi
        return
    fi

    # Normal directory: replace $HOME with ~
    local dir="${cwd/#$HOME/~}"
    echo -ne "${C_BLUE}${dir}${C_RESET}"
}

# =============================================================================
# Git status (brute.zsh-theme style: ± branch [shorthash] !?+)
# =============================================================================

render_git() {
    local cwd="${1:-}"
    [[ -z "$cwd" || ! -d "$cwd" ]] && return

    local branch
    branch=$(git -C "$cwd" --no-optional-locks rev-parse --abbrev-ref HEAD 2>/dev/null) || return

    local hash
    hash=$(git -C "$cwd" --no-optional-locks rev-parse --short=8 HEAD 2>/dev/null) || hash=""

    # Status indicators matching brute theme: ! for unstaged, ? for untracked, + for staged
    local indicators=""
    local status_output
    status_output=$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null) || status_output=""

    if echo "$status_output" | grep -q '^.[MDRC]'; then
        indicators+="${C_YELLOW}!${C_RESET}"
    fi
    if echo "$status_output" | grep -q '^??'; then
        indicators+="${C_YELLOW}?${C_RESET}"
    fi
    if echo "$status_output" | grep -q '^[MADRC]'; then
        indicators+="${C_GREEN}+${C_RESET}"
    fi
    if [[ -n "$indicators" ]]; then
        indicators=" ${indicators}"
    fi

    echo -ne "${C_GRAY}± ${C_MAGENTA}${branch} ${C_GRAY}[${hash}]${indicators}${C_RESET}"
}

# =============================================================================
# Worker Status Line
# =============================================================================

render_worker_status() {
    local worker_id="$1"
    local context_pct="${2:-0}"
    local cost="${3:-}"

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

    [[ -z "$worker_info" ]] && return 1

    local issue pr_num stage
    IFS='|' read -r issue pr_num stage <<< "$worker_info"

    local parts="${C_MAGENTA}#${issue}${C_RESET}"
    if [[ "$pr_num" != "0" && -n "$pr_num" ]]; then
        parts+=" ${C_GRAY}→${C_RESET} ${C_GREEN}PR #${pr_num}${C_RESET}"
    fi
    parts+=" ${C_GRAY}|${C_RESET} ${stage}"

    local cost_str
    cost_str=$(render_cost "$cost")
    if [[ -n "$cost_str" ]]; then
        parts+=" ${C_GRAY}|${C_RESET} ${cost_str}"
    fi

    parts+=" ${C_GRAY}|${C_RESET} $(render_context_bar "$context_pct")"

    echo -e "$parts"
}

# =============================================================================
# Main
# =============================================================================

CWD=$(echo "$INPUT" | jq -r '.workspace.current_dir // empty' 2>/dev/null)
CONTEXT_PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // 0' 2>/dev/null || echo "0")
CONTEXT_PCT=${CONTEXT_PCT%.*}
COST_USD=$(echo "$INPUT" | jq -r '.cost.total_cost_usd // empty' 2>/dev/null)

# Worker session: compact issue/PR/stage view
if [[ -n "${WORK_WORKER_ID:-}" ]]; then
    if render_worker_status "$WORK_WORKER_ID" "$CONTEXT_PCT" "$COST_USD"; then
        exit 0
    fi
fi

# Normal session: dir (git) | $cost | context_bar
parts=""

dir_str=$(render_dir "$CWD")
if [[ -n "$dir_str" ]]; then
    parts+="$dir_str"
fi

git_str=$(render_git "$CWD")
if [[ -n "$git_str" ]]; then
    parts+=" $git_str"
fi

cost_str=$(render_cost "$COST_USD")
if [[ -n "$cost_str" ]]; then
    parts+=" ${C_GRAY}|${C_RESET} ${cost_str}"
fi

parts+=" ${C_GRAY}|${C_RESET} $(render_context_bar "$CONTEXT_PCT")"

echo -e "$parts"
