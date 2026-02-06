#!/bin/bash
# work-session-end.sh - Claude Code SessionEnd hook for marking workers as done
#
# This SessionEnd hook fires when a Claude Code session terminates
# (Ctrl-C, /exit, tab close, etc.). It marks the current worker as done
# so it doesn't appear as "failed" from stale PID cleanup.

set -euo pipefail

# Check if we're in a worker session
if [[ -z "${WORK_WORKER_ID:-}" ]]; then
    exit 0
fi

DB_PATH="${WORK_DB_PATH:-${HOME}/.worktrees/work-sessions.db}"

# Log that the hook fired (for debugging - remove once verified)
HOOK_INPUT=$(cat)
REASON=$(echo "$HOOK_INPUT" | jq -r '.reason // "unknown"' 2>/dev/null || echo "unknown")
echo "$(date -u '+%Y-%m-%d %H:%M:%S') session-end hook fired for worker ${WORK_WORKER_ID} reason=${REASON}" >> /tmp/work-session-end-hook.log

# Only mark as done if the worker isn't already done/failed
sqlite3 "$DB_PATH" "
    UPDATE workers
    SET status='done', stage='done', updated_at=datetime('now')
    WHERE id=${WORK_WORKER_ID}
      AND status NOT IN ('done', 'failed')
" 2>/dev/null || true

exit 0
