#!/bin/bash
# work-stop.sh - Claude Code Stop hook for marking workers as done on exit
#
# This Stop hook fires when Claude Code shuts down (e.g., Ctrl-C, /exit).
# It marks the current worker as done so it doesn't appear as "failed"
# from stale PID cleanup.

set -euo pipefail

# Check if we're in a worker session
if [[ -z "${WORK_WORKER_ID:-}" ]]; then
    exit 0
fi

DB_PATH="${WORK_DB_PATH:-${HOME}/.worktrees/work-sessions.db}"

# Only mark as done if the worker isn't already done/failed
sqlite3 "$DB_PATH" "
    UPDATE workers
    SET status='done', stage='done', updated_at=datetime('now')
    WHERE id=${WORK_WORKER_ID}
      AND status NOT IN ('done', 'failed')
" 2>/dev/null || true

exit 0
