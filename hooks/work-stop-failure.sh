#!/bin/bash
# work-stop-failure.sh - Claude Code StopFailure hook
#
# Fires when the model hits an error (rate limit, overload, API error).
# Marks the worker as failed and logs the error so it shows up in `work --status`
# and `work --events`.

set -euo pipefail

# Only act inside a worker session
if [[ -z "${WORK_WORKER_ID:-}" ]]; then
    exit 0
fi

DB_PATH="${WORK_DB_PATH:-${HOME}/.worktrees/work-sessions.db}"

HOOK_INPUT=$(cat)
ERROR=$(echo "$HOOK_INPUT" | jq -r '.error // "unknown"' 2>/dev/null || echo "unknown")
ERROR_DETAILS=$(echo "$HOOK_INPUT" | jq -r '.error_details // ""' 2>/dev/null || echo "")

# Build a compact message: "overloaded_error: upstream overloaded" or just the error type
if [[ -n "$ERROR_DETAILS" ]]; then
    MESSAGE="StopFailure: ${ERROR}: ${ERROR_DETAILS}"
else
    MESSAGE="StopFailure: ${ERROR}"
fi
# Truncate to avoid blowing up the DB column
MESSAGE="${MESSAGE:0:500}"
# Escape single quotes for SQLite ('' is the SQL escape for ')
SQL_MESSAGE=$(printf '%s' "$MESSAGE" | sed "s/'/''/g")

sqlite3 "$DB_PATH" "
    UPDATE workers
    SET status='failed', updated_at=datetime('now')
    WHERE id=${WORK_WORKER_ID}
      AND status NOT IN ('done', 'failed');

    INSERT INTO events (worker_id, event_type, message)
    VALUES (${WORK_WORKER_ID}, 'failed', '${SQL_MESSAGE}');
" 2>/dev/null || true

exit 0
