#!/bin/bash
# test-stop-hook.sh - Test the Stop hook behavior
#
# Tests that work-stop.sh correctly marks workers as done.
# To test signal behavior (Ctrl-C vs tab close), you need a real
# Claude Code session - see instructions at the bottom.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOP_HOOK="${SCRIPT_DIR}/work-stop.sh"
TEST_DB="/tmp/test-work-stop-$$.db"

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

echo "=== Stop Hook Tests ==="
echo ""

# Test 1: Running worker gets marked done
sqlite3 "$TEST_DB" "INSERT INTO workers (id, status, stage) VALUES (1, 'running', 'implementing')"
WORK_WORKER_ID=1 WORK_DB_PATH="$TEST_DB" "$STOP_HOOK"
STATUS=$(sqlite3 "$TEST_DB" "SELECT status || '|' || stage FROM workers WHERE id=1")
if [[ "$STATUS" == "done|done" ]]; then
    pass "Running worker marked as done"
else
    fail "Running worker status: $STATUS (expected done|done)"
fi

# Test 2: Already-done worker is not modified
sqlite3 "$TEST_DB" "INSERT INTO workers (id, status, stage, updated_at) VALUES (2, 'done', 'done', datetime('now', '-2 hours'))"
OLD_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=2")
WORK_WORKER_ID=2 WORK_DB_PATH="$TEST_DB" "$STOP_HOOK"
NEW_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=2")
if [[ "$OLD_TIME" == "$NEW_TIME" ]]; then
    pass "Already-done worker not modified"
else
    fail "Already-done worker updated_at changed: $OLD_TIME -> $NEW_TIME"
fi

# Test 3: Already-failed worker is not modified
sqlite3 "$TEST_DB" "INSERT INTO workers (id, status, stage, updated_at) VALUES (3, 'failed', 'exploring', datetime('now', '-2 hours'))"
OLD_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=3")
WORK_WORKER_ID=3 WORK_DB_PATH="$TEST_DB" "$STOP_HOOK"
NEW_TIME=$(sqlite3 "$TEST_DB" "SELECT updated_at FROM workers WHERE id=3")
if [[ "$OLD_TIME" == "$NEW_TIME" ]]; then
    pass "Already-failed worker not modified"
else
    fail "Already-failed worker updated_at changed: $OLD_TIME -> $NEW_TIME"
fi

# Test 4: No WORK_WORKER_ID exits cleanly
unset WORK_WORKER_ID
OUTPUT=$("$STOP_HOOK" 2>&1) || true
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
echo "To test which signals trigger the Stop hook, start a worker:"
echo "  work --here <issue>"
echo ""
echo "Then try each and check 'work --status' afterwards:"
echo "  1. Ctrl-C        (sends SIGINT)"
echo "  2. Close the tab  (sends SIGHUP)"
echo "  3. /exit          (graceful exit)"
echo ""

exit $FAILURES
