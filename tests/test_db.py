"""Tests for database operations."""

import pytest

from conftest import work


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_init_creates_tables(self, temp_db):
        """init_db should create all required tables."""
        work.init_db()

        # Verify tables exist by querying them
        with work.get_db() as conn:
            # Should not raise
            conn.execute("SELECT * FROM workers LIMIT 1")
            conn.execute("SELECT * FROM events LIMIT 1")
            conn.execute("SELECT * FROM completions LIMIT 1")
            conn.execute("SELECT * FROM messages LIMIT 1")
            conn.execute("SELECT * FROM sessions LIMIT 1")

    def test_init_is_idempotent(self, temp_db):
        """Calling init_db multiple times should not error."""
        work.init_db()
        work.init_db()
        work.init_db()

        with work.get_db() as conn:
            result = conn.execute("SELECT COUNT(*) FROM workers").fetchone()
            assert result[0] == 0


class TestWorkerRegistration:
    """Tests for worker registration and lookup."""

    def test_register_worker(self, initialized_db):
        """Should register a worker and return its ID."""
        worker_id = work.db_register_worker(
            repo_path="/path/to/repo",
            repo_name="myrepo",
            issue_number=42,
            branch="issue-42",
            worktree_path="/path/to/worktree",
            pid=1234,
        )

        assert worker_id is not None
        assert isinstance(worker_id, int)

    def test_register_worker_with_jira(self, initialized_db):
        """Should register a JIRA-based worker."""
        worker_id = work.db_register_worker(
            repo_path="/path/to/repo",
            repo_name="myrepo",
            issue_number=None,
            branch="AIE-123-feature",
            worktree_path="/path/to/worktree",
            pid=1234,
            jira_key="AIE-123",
            issue_source="jira",
        )

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT jira_key, issue_source FROM workers WHERE id = ?",
                (worker_id,)
            ).fetchone()
            assert row["jira_key"] == "AIE-123"
            assert row["issue_source"] == "jira"

    def test_register_worker_default_values(self, initialized_db):
        """New workers should have correct default status/stage."""
        worker_id = work.db_register_worker(
            repo_path="/path/to/repo",
            repo_name="myrepo",
            issue_number=1,
            branch="issue-1",
            worktree_path="/path/to/worktree",
            pid=1111,
        )

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT status, phase, stage FROM workers WHERE id = ?",
                (worker_id,)
            ).fetchone()
            assert row["status"] == "starting"
            assert row["phase"] == "implementation"
            assert row["stage"] == "exploring"

    def test_register_replaces_existing(self, initialized_db):
        """Registering same repo+branch should replace."""
        work.db_register_worker(
            repo_path="/path/to/repo",
            repo_name="myrepo",
            issue_number=42,
            branch="issue-42",
            worktree_path="/path/to/worktree",
            pid=1111,
        )

        # Register again with different PID
        worker_id = work.db_register_worker(
            repo_path="/path/to/repo",
            repo_name="myrepo",
            issue_number=42,
            branch="issue-42",
            worktree_path="/path/to/worktree",
            pid=2222,
        )

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT pid FROM workers WHERE id = ?",
                (worker_id,)
            ).fetchone()
            assert row["pid"] == 2222

            # Should only be one worker
            count = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
            assert count == 1


class TestStatusUpdates:
    """Tests for status and stage updates."""

    def test_update_status(self, sample_worker):
        """Should update worker status."""
        work.db_update_status(sample_worker, "running")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT status FROM workers WHERE id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["status"] == "running"

    def test_update_status_with_phase(self, sample_worker):
        """Should update status and phase together."""
        work.db_update_status(sample_worker, "pr_open", phase="ci_review")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT status, phase FROM workers WHERE id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["status"] == "pr_open"
            assert row["phase"] == "ci_review"

    def test_update_stage_valid(self, sample_worker):
        """Should update stage with valid value."""
        work.db_update_stage(sample_worker, "implementing")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT stage FROM workers WHERE id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["stage"] == "implementing"

    def test_update_stage_invalid_raises(self, sample_worker):
        """Should raise for invalid stage."""
        with pytest.raises(Exception) as exc_info:
            work.db_update_stage(sample_worker, "invalid_stage")

        assert "Invalid stage" in str(exc_info.value)

    def test_update_stage_logs_event(self, sample_worker):
        """Stage changes should be logged as events."""
        work.db_update_stage(sample_worker, "testing")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT event_type, message FROM events WHERE worker_id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["event_type"] == "stage_change"
            assert "testing" in row["message"]


class TestPrTracking:
    """Tests for PR tracking."""

    def test_update_pr(self, sample_worker):
        """Should update PR number and URL."""
        work.db_update_pr(sample_worker, 99, "https://github.com/org/repo/pull/99")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT pr_number, pr_url, status, phase FROM workers WHERE id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["pr_number"] == 99
            assert row["pr_url"] == "https://github.com/org/repo/pull/99"
            assert row["status"] == "pr_open"
            assert row["phase"] == "ci_review"


class TestEventLogging:
    """Tests for event logging."""

    def test_log_event(self, sample_worker):
        """Should log events for a worker."""
        work.db_log_event(sample_worker, "test_event", "Test message")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT event_type, message FROM events WHERE worker_id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["event_type"] == "test_event"
            assert row["message"] == "Test message"

    def test_multiple_events(self, sample_worker):
        """Should track multiple events in order."""
        work.db_log_event(sample_worker, "event1", "First")
        work.db_log_event(sample_worker, "event2", "Second")
        work.db_log_event(sample_worker, "event3", "Third")

        with work.get_db() as conn:
            rows = conn.execute(
                "SELECT event_type FROM events WHERE worker_id = ? ORDER BY id",
                (sample_worker,)
            ).fetchall()
            types = [r["event_type"] for r in rows]
            assert types == ["event1", "event2", "event3"]


class TestMessageQueue:
    """Tests for the message queue."""

    def test_send_message(self, sample_worker):
        """Should queue a message for a worker."""
        # Signature: db_send_message(worker_id, message_type, payload)
        work.db_send_message(sample_worker, "info", "Test payload")

        with work.get_db() as conn:
            row = conn.execute(
                "SELECT payload, message_type, read_at FROM messages WHERE worker_id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["payload"] == "Test payload"
            assert row["message_type"] == "info"
            assert row["read_at"] is None

    def test_get_messages_unread(self, sample_worker):
        """Should retrieve unread messages."""
        work.db_send_message(sample_worker, "info", "Message 1")
        work.db_send_message(sample_worker, "info", "Message 2")

        messages = work.db_get_messages(sample_worker, mark_read=False)
        assert len(messages) == 2

    def test_get_messages_marks_read(self, sample_worker):
        """Getting messages with mark_read=True should mark them."""
        work.db_send_message(sample_worker, "info", "Message 1")

        # First call gets the message
        messages = work.db_get_messages(sample_worker, mark_read=True)
        assert len(messages) == 1

        # Second call should get nothing (already read)
        messages = work.db_get_messages(sample_worker, mark_read=True)
        assert len(messages) == 0


class TestCompletion:
    """Tests for worker completion tracking."""

    def test_store_completion(self, sample_worker):
        """Should store completion and mark worker done."""
        work.db_store_completion(
            worker_id=sample_worker,
            summary="Fixed the bug",
            files_changed="src/main.py",
            tests_added="tests/test_main.py",
            pr_url="https://github.com/org/repo/pull/42",
            merged=True,
            follow_up_issues="",
            lessons_learned="Always write tests first",
        )

        with work.get_db() as conn:
            # Check completion record
            row = conn.execute(
                "SELECT summary, merged FROM completions WHERE worker_id = ?",
                (sample_worker,)
            ).fetchone()
            assert row["summary"] == "Fixed the bug"
            assert row["merged"] == 1  # SQLite stores bool as int

            # Check worker status
            status = conn.execute(
                "SELECT status FROM workers WHERE id = ?",
                (sample_worker,)
            ).fetchone()
            assert status["status"] == "done"


class TestWorkerLookup:
    """Tests for looking up workers by various identifiers."""

    def test_get_worker_by_issue_number(self, sample_worker):
        """Should find worker by issue number."""
        # sample_worker has issue_number=42
        found = work.db_get_worker_by_issue("42", repo_name="myrepo")
        assert found == sample_worker

    def test_get_worker_by_jira_key(self, initialized_db):
        """Should find worker by JIRA key."""
        worker_id = work.db_register_worker(
            repo_path="/path/to/repo",
            repo_name="myrepo",
            issue_number=None,
            branch="AIE-999-feature",
            worktree_path="/path/to/worktree",
            pid=1234,
            jira_key="AIE-999",
            issue_source="jira",
        )

        found = work.db_get_worker_by_issue("AIE-999")
        assert found == worker_id

    def test_get_worker_not_found(self, initialized_db):
        """Should return None for non-existent worker."""
        found = work.db_get_worker_by_issue("99999")
        assert found is None


class TestValidStages:
    """Tests for stage validation."""

    def test_all_valid_stages_accepted(self, sample_worker):
        """All defined stages should be accepted."""
        for stage in work.VALID_STAGES:
            work.db_update_stage(sample_worker, stage)
            with work.get_db() as conn:
                row = conn.execute(
                    "SELECT stage FROM workers WHERE id = ?",
                    (sample_worker,)
                ).fetchone()
                assert row["stage"] == stage


class TestSessionsTable:
    """Tests for the sessions tracking table."""

    def test_sessions_table_created(self, initialized_db):
        """Sessions table should be created on init."""
        with work.get_db() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            assert cursor.fetchone() is not None

    def test_sessions_table_has_expected_columns(self, initialized_db):
        """Sessions table should have all required columns."""
        with work.get_db() as conn:
            cursor = conn.execute("PRAGMA table_info(sessions)")
            columns = {row[1] for row in cursor.fetchall()}
            expected = {
                "id", "worker_id", "session_number", "session_id",
                "started_at", "ended_at", "end_reason", "context_at_end", "summary"
            }
            assert expected.issubset(columns)

    def test_sessions_index_created(self, initialized_db):
        """Index on worker_id should exist."""
        with work.get_db() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sessions_worker'"
            )
            assert cursor.fetchone() is not None
