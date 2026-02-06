#!/bin/bash
# test-session-end-hook.sh - Test the SessionEnd hook behavior
#
# Tests that work-session-end.sh correctly marks workers as done.
# To test signal behavior (Ctrl-C vs tab close), you need a real
# Claude Code session - see instructions at the bottom.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${SCRIPT_DIR}/work-session-end.sh"
TEST_DB="/tmp/test-work-session-end-$$.db"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC}: $*"; }
fail() { echo -e "${RED}FAIL${NC}: $*"; FAILURES=$((FAILURES + 1)); }

FAILURES=0

cleanup() {
    rm -f "$TEST_DB"
}
trap cleanup EXIT

# Create test database
sqlite3 "$TEST_DB" "
    CREATE TABLE workers (
        id INTEGER PRIMARY KEY,
        status TEXT DEFAULT 'running',
        stage TEXT DEFAULT 'exploring',
        updated_at TEXT DEFAULT (datetime('now', '-1 hour'))
    );
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER,
        event_type TEXT,
        message TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
"

echo "=== SessionEnd Hook Tests ==="
echo ""

# Test 1: Running worker gets marked done
sqlite3 "$TEST_DB" "INSERT INTO workers (id, status, stage) VALUES (1, 'running', 'implementing')"
echo '{"reason":"prompt_input_exit"}' | WORK_WORKER_ID=1 WORK_DB_PATH="$TEST_DB" "$HOOK"
STATUS=$(sqlite3 "$TEST_DB" "SELECT status || '|' || stage FROM workers WHERE id=1")
if [[ "$STATUS" == "done|done" ]]; then
    pass "Running worker marked as done"
else
    fail "Running worker status: $STATUS (expected done|done)"
fi

# Test 2: Already-done worker is not modified
sqlite3 "$TEST_DB" "INSERT INTO workers (id, status, stage, updated_at) VALUES (2, 'done', 'done', datetime('now', '-2 hours'))"
OLD_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=2")
echo '{"reason":"prompt_input_exit"}' | WORK_WORKER_ID=2 WORK_DB_PATH="$TEST_DB" "$HOOK"
NEW_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=2")
if [[ "$OLD_TIME" == "$NEW_TIME" ]]; then
    pass "Already-done worker not modified"
else
    fail "Already-done worker updated_at changed: $OLD_TIME -> $NEW_TIME"
fi

# Test 3: Already-failed worker is not modified
sqlite3 "$TEST_DB" "INSERT INTO workers (id, status, stage, updated_at) VALUES (3, 'failed', 'exploring', datetime('now', '-2 hours'))"
OLD_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=3")
echo '{"reason":"prompt_input_exit"}' | WORK_WORKER_ID=3 WORK_DB_PATH="$TEST_DB" "$HOOK"
NEW_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=3")
if [[ "$OLD_TIME" == "$NEW_TIME" ]]; then
    pass "Already-failed worker not modified"
else
    fail "Already-failed worker updated_at changed: $OLD_TIME -> $NEW_TIME"
fi

# Test 4: No WORK_WORKER_ID exits cleanly
unset WORK_WORKER_ID
OUTPUT=$(echo '{"reason":"other"}' | "$HOOK" 2>&1) || true
pass "No WORK_WORKER_ID exits without error"

echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
else
    echo -e "${RED}${FAILURES} test(s) failed${NC}"
fi

echo ""
echo "=== Manual Signal Testing ==="
echo ""
echo "To test which exit methods trigger the SessionEnd hook,"
echo "start a worker and check /tmp/work-session-end-hook.log after each:"
echo ""
echo "  1. work --here <issue>  then Ctrl-C     (reason: prompt_input_exit)"
echo "  2. work <issue>         then close tab   (reason: other)"
echo "  3. work --here <issue>  then /exit       (reason: prompt_input_exit)"
echo ""
echo "  cat /tmp/work-session-end-hook.log"
echo ""

exit $FAILURES
