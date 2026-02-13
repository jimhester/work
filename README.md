# work

A CLI for running Claude Code sessions against GitHub issues and JIRA tickets.
Each issue gets its own git worktree so you can run multiple in parallel without
branch conflicts.

## What it does

You point it at an issue number, and it:

1. Creates a git worktree in `~/.worktrees/{repo}/{branch}`
2. Opens a new terminal tab (iTerm2 or Windows Terminal)
3. Starts Claude Code with a structured prompt covering the full lifecycle:
   read the issue, plan, implement, test, open a PR, wait for CI, respond to
   review, merge

State is tracked in a SQLite database (`~/.worktrees/work-sessions.db`), so
you can check on workers, send them messages, or resume crashed sessions from
the parent terminal.

## Setup

The script runs via `uv run --script`, so dependencies (click, tomli) are
handled automatically. You do need `jq` and `sqlite3` on your PATH.

Run `work --init` inside a repo to set everything up: hooks, skills, status
line, and a `.work.toml` config file. If a `CLAUDE.md` exists in the repo it
will generate project-specific worker and review guidelines from it.

## Usage

```
./work 42                         # spawn a worker for issue #42
./work 97 98 99                   # spawn three workers in parallel
./work https://github.com/...     # works with URLs too
./work PROJ-123                   # JIRA keys (requires acli)
./work --here 42                  # run in the current terminal instead
./work "add retry logic"          # feature branch, no issue
```

### Monitoring

```
./work --status                   # list active workers with stage, PR, idle time
./work --events                   # recent event log
./work --logs 42                  # stream a worker's output
./work --send 42 "check the new spec"   # send a message to a worker
```

### Review and merge

Workers are blocked from creating PRs or merging until they pass a self-review
(`work --review`). This is enforced by a PreToolUse hook that checks for an
`APPROVED` marker file in the repo root. The review itself runs a diff-based
checklist that can be customized in `.work.toml`.

```
./work --review                   # self-review before PR
./work --review --pre-merge       # stricter review before merge
./work --reviews                  # show review history (stored as git notes)
```

### Recovery

```
./work --resume                   # interactive picker to resume crashed workers
./work --cleanup                  # kill orphaned processes
```

### Context management

Long sessions can run into context limits. Two escape hatches:

`/trim` truncates large tool outputs in the session file and gives you a
resume command. Typically frees 30-50% of context.

`/rollover` writes a handoff summary to episodic-memory and starts a fresh
session. Better for when you're switching to a new phase of work or trim
wouldn't recover enough space.

## Configuration

The `.work.toml` created by `--init` controls worker guidelines (appended to
the prompt), review checklists, review strictness, and context thresholds.

## How the hooks work

Two Claude Code hooks get installed into `~/.claude/hooks/`:

**Stage detector** (PostToolUse) watches Bash output for patterns like
`gh pr create`, `gh pr checks`, `gh pr merge`, and merge conflicts. When it
sees one, it updates the worker's stage in the database. It also checks for
pending messages and monitors context usage.

**Review guard** (PreToolUse) blocks `gh pr create` and `gh pr merge` unless
a `.work-review-status` file exists, is newer than the last commit, and
contains "APPROVED".

## Project layout

```
work              main script (Python, ~3500 lines)
hooks/            Claude Code hooks + installer + tests
skills/           skill definitions for Claude Code (work, trim, rollover)
tests/            pytest suite
```

## Dependencies

Python >= 3.11, click >= 8.0, tomli >= 2.0 (managed by uv). Shell tools: jq,
sqlite3, git. Optional: GitHub CLI (gh or ghe), Atlassian CLI (acli) for JIRA.
