# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains the `work` tool - a CLI for spawning and managing isolated Claude Code sessions for GitHub issues and JIRA tickets using git worktrees. It includes:

- **`work`**: Main Python script (runs via `uv run --script`) for worker spawning and management
- **`hooks/`**: Claude Code hooks for automatic stage detection and review enforcement
- **`skills/work/`**: Skill definition for Claude Code integration

## Architecture

### Worker Management

The `work` script creates isolated Claude Code sessions:
1. Parses GitHub issue/PR URLs, issue numbers, or JIRA keys
2. Creates/reuses a git worktree at `~/.worktrees/{repo}/{branch}`
3. Registers worker in SQLite database (`~/.worktrees/work-sessions.db`)
4. Starts Claude Code with a structured prompt for end-to-end task completion
5. Tracks worker status, stage, and PR information

### Database Schema

SQLite database with four tables:
- `workers`: Active worker metadata (repo, issue, branch, PID, status, stage, pr_number, jira_key)
- `events`: History of status changes, stage transitions
- `completions`: Final summaries when workers complete
- `messages`: Parent-to-worker message queue

### Hook System

Two Claude Code hooks installed via `hooks/install-hooks.sh`:

1. **`work-stage-detector.sh`** (PostToolUse): Monitors Bash commands to auto-detect:
   - PR creation (`gh pr create`) → sets stage to `ci_waiting`
   - CI passing (`gh pr checks`) → sets stage to `review_waiting`
   - PR merge (`gh pr merge`) → sets stage to `done`
   - Merge conflicts → sets stage to `merge_conflicts`

2. **`work-review-guard.sh`** (PreToolUse): Blocks PR operations unless:
   - `.work-review-status` file exists in repo root
   - File is newer than last commit
   - File contains "APPROVED"

### Worker Stages

Valid stages: `exploring`, `planning`, `implementing`, `testing`, `pr_creating`, `ci_waiting`, `review_waiting`, `review_responding`, `merge_conflicts`, `done`, `blocked`

## Development

### Dependencies

The `work` script uses inline script metadata (`uv run --script`):
- Python >= 3.11
- click >= 8.0
- tomli >= 2.0

Hooks require: `jq`, `sqlite3`

### Running the Script

```bash
# Direct execution (uv handles dependencies)
./work 42                    # Spawn worker for issue #42
./work --here 42             # Run in current terminal
./work --status              # Show active workers
./work --review              # Run self-review before PR
./work --init                # Create .work.toml config
```

### Testing Hooks

```bash
# Test the review guard hook
./hooks/test-review-hook.sh

# Manually install hooks
./hooks/install-hooks.sh
```

### Project Configuration

Per-repo configuration via `.work.toml`:
- `worker_guidelines`: Instructions appended to worker prompt
- `review_guidelines`: Checklist for self-reviewing code
- `review_strictness`: "strict" | "normal" | "lenient"
- `require_pre_merge_review`: bool
- `review_exclude_patterns`: Files to exclude from review diff (defaults to lock files)

## Key Patterns

- Environment variables `WORK_WORKER_ID` and `WORK_DB_PATH` are set for workers
- Terminal spawning: iTerm2 on macOS, Windows Terminal on WSL
- GitHub CLI detection: uses `ghe` for github.netflix.net remotes, `gh` otherwise
- JIRA support requires `acli` CLI to be installed and authenticated

### Context Management

Workers can manage context proactively:

- **`/trim`**: Removes large tool outputs, staying in session (30-50% savings)
- **`/rollover`**: Starts fresh session with handoff summary + episodic-memory

Hook warnings appear at 60%, 75%, and 85% context usage.

Configuration in `.work.toml`:
```toml
[context]
warn_threshold = 60
recommend_threshold = 75
urgent_threshold = 85
trim_threshold_chars = 500
```
