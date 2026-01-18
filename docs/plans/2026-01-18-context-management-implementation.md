# Context Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `/trim` and `/rollover` skills to manage worker context proactively before quality degrades.

**Architecture:** Hook-based warnings at thresholds, `/trim` skill modifies session JSONL to truncate large tool outputs, `/rollover` skill starts fresh session with handoff summary and episodic-memory retrieval.

**Tech Stack:** Python (work script), Bash (hooks), SQLite (sessions table), Claude Code skills

---

## Task 1: Add Sessions Table to Database Schema

**Files:**
- Modify: `work:140-197` (SCHEMA constant)
- Modify: `tests/test_db.py` (add new test class)

**Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
class TestSessionsTable:
    """Tests for the sessions tracking table."""

    def test_sessions_table_created(self, initialized_db):
        """Sessions table should be created on init."""
        cursor = initialized_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )
        assert cursor.fetchone() is not None

    def test_sessions_table_has_expected_columns(self, initialized_db):
        """Sessions table should have all required columns."""
        cursor = initialized_db.execute("PRAGMA table_info(sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "id", "worker_id", "session_number", "session_id",
            "started_at", "ended_at", "end_reason", "context_at_end", "summary"
        }
        assert expected.issubset(columns)

    def test_sessions_index_created(self, initialized_db):
        """Index on worker_id should exist."""
        cursor = initialized_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sessions_worker'"
        )
        assert cursor.fetchone() is not None
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_db.py::TestSessionsTable -v`

Expected: FAIL with "no such table: sessions"

**Step 3: Add sessions table to SCHEMA**

Modify `work` SCHEMA constant (around line 140), add before the final `"""`):

```python
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    worker_id INTEGER REFERENCES workers(id),
    session_number INTEGER,
    session_id TEXT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    end_reason TEXT,
    context_at_end INTEGER,
    summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_worker ON sessions(worker_id);
```

**Step 4: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_db.py::TestSessionsTable -v`

Expected: PASS (3 tests)

**Step 5: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: 110 passed (107 original + 3 new)

**Step 6: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_db.py && git commit -m "feat(db): add sessions table for context management tracking"
```

---

## Task 2: Add Session CRUD Functions

**Files:**
- Modify: `work` (add functions after database section ~line 280)
- Modify: `tests/test_db.py` (add tests)

**Step 1: Write the failing tests**

Add to `tests/test_db.py`:

```python
class TestSessionCRUD:
    """Tests for session create/read/update functions."""

    def test_create_session(self, initialized_db, sample_worker):
        """Should create a new session record."""
        session_id = work.create_session(
            initialized_db,
            worker_id=sample_worker,
            session_number=1,
            claude_session_id="uuid-123"
        )
        assert session_id is not None

        cursor = initialized_db.execute(
            "SELECT worker_id, session_number, session_id FROM sessions WHERE id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        assert row[0] == sample_worker
        assert row[1] == 1
        assert row[2] == "uuid-123"

    def test_end_session(self, initialized_db, sample_worker):
        """Should update session with end info."""
        session_id = work.create_session(
            initialized_db,
            worker_id=sample_worker,
            session_number=1,
        )

        work.end_session(
            initialized_db,
            session_id=session_id,
            end_reason="rollover",
            context_at_end=75,
            summary="Test summary"
        )

        cursor = initialized_db.execute(
            "SELECT end_reason, context_at_end, summary, ended_at FROM sessions WHERE id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        assert row[0] == "rollover"
        assert row[1] == 75
        assert row[2] == "Test summary"
        assert row[3] is not None  # ended_at set

    def test_get_current_session_number(self, initialized_db, sample_worker):
        """Should return highest session number for worker."""
        work.create_session(initialized_db, worker_id=sample_worker, session_number=1)
        work.create_session(initialized_db, worker_id=sample_worker, session_number=2)

        result = work.get_current_session_number(initialized_db, sample_worker)
        assert result == 2

    def test_get_current_session_number_no_sessions(self, initialized_db, sample_worker):
        """Should return 0 when no sessions exist."""
        result = work.get_current_session_number(initialized_db, sample_worker)
        assert result == 0
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_db.py::TestSessionCRUD -v`

Expected: FAIL with "module 'work' has no attribute 'create_session'"

**Step 3: Implement session CRUD functions**

Add to `work` after the existing database functions (around line 280):

```python
def create_session(
    db: sqlite3.Connection,
    worker_id: int,
    session_number: int,
    claude_session_id: str = None,
) -> int:
    """Create a new session record for a worker."""
    cursor = db.execute(
        """
        INSERT INTO sessions (worker_id, session_number, session_id)
        VALUES (?, ?, ?)
        """,
        (worker_id, session_number, claude_session_id),
    )
    db.commit()
    return cursor.lastrowid


def end_session(
    db: sqlite3.Connection,
    session_id: int,
    end_reason: str,
    context_at_end: int = None,
    summary: str = None,
) -> None:
    """Mark a session as ended with metadata."""
    db.execute(
        """
        UPDATE sessions
        SET ended_at = CURRENT_TIMESTAMP,
            end_reason = ?,
            context_at_end = ?,
            summary = ?
        WHERE id = ?
        """,
        (end_reason, context_at_end, summary, session_id),
    )
    db.commit()


def get_current_session_number(db: sqlite3.Connection, worker_id: int) -> int:
    """Get the highest session number for a worker, or 0 if none."""
    cursor = db.execute(
        "SELECT MAX(session_number) FROM sessions WHERE worker_id = ?",
        (worker_id,),
    )
    result = cursor.fetchone()[0]
    return result if result is not None else 0
```

**Step 4: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_db.py::TestSessionCRUD -v`

Expected: PASS (4 tests)

**Step 5: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: 114 passed

**Step 6: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_db.py && git commit -m "feat(db): add session CRUD functions"
```

---

## Task 3: Add ContextConfig to Configuration

**Files:**
- Modify: `work:60-83` (after WorkConfig class)
- Modify: `work:85-113` (load_work_config function)
- Modify: `tests/test_config.py`

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
class TestContextConfig:
    """Tests for context management configuration."""

    def test_default_context_thresholds(self):
        """Should have sensible default thresholds."""
        config = work.ContextConfig()
        assert config.warn_threshold == 60
        assert config.recommend_threshold == 75
        assert config.urgent_threshold == 85

    def test_default_trim_settings(self):
        """Should have default trim settings."""
        config = work.ContextConfig()
        assert config.trim_threshold_chars == 500
        assert "Read" in config.trim_target_tools
        assert "Bash" in config.trim_target_tools

    def test_load_context_config_from_file(self, tmp_path, monkeypatch):
        """Should load context config from .work.toml."""
        config_file = tmp_path / ".work.toml"
        config_file.write_text('''
[context]
warn_threshold = 50
recommend_threshold = 70
urgent_threshold = 80
trim_threshold_chars = 300
''')
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()
        assert config.context.warn_threshold == 50
        assert config.context.recommend_threshold == 70
        assert config.context.urgent_threshold == 80
        assert config.context.trim_threshold_chars == 300

    def test_context_config_defaults_when_not_in_file(self, tmp_path, monkeypatch):
        """Should use defaults when [context] section missing."""
        config_file = tmp_path / ".work.toml"
        config_file.write_text('worker_guidelines = "test"')
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()
        assert config.context.warn_threshold == 60
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_config.py::TestContextConfig -v`

Expected: FAIL with "module 'work' has no attribute 'ContextConfig'"

**Step 3: Add ContextConfig dataclass**

Add after `WorkConfig` class (around line 83):

```python
@dataclass
class ContextConfig:
    """Context management configuration."""
    warn_threshold: int = 60
    recommend_threshold: int = 75
    urgent_threshold: int = 85
    trim_threshold_chars: int = 500
    trim_target_tools: list = None
    check_interval_seconds: int = 60

    def __post_init__(self):
        if self.trim_target_tools is None:
            self.trim_target_tools = ["Read", "Bash", "Grep", "Glob"]
```

**Step 4: Add context field to WorkConfig**

Modify `WorkConfig` class to add context field:

```python
@dataclass
class WorkConfig:
    """Project-specific work configuration from .work.toml."""
    worker_guidelines: str = ""
    review_guidelines: str = ""
    review_strictness: str = "normal"
    require_pre_merge_review: bool = True
    review_exclude_patterns: list = None
    context: ContextConfig = None  # Add this line

    def __post_init__(self):
        if self.review_exclude_patterns is None:
            self.review_exclude_patterns = [
                "*.lock",
                "package-lock.json",
                # ... existing patterns ...
            ]
        if self.context is None:  # Add this block
            self.context = ContextConfig()
```

**Step 5: Update load_work_config to load context section**

Modify `load_work_config()` function, add after existing config loading:

```python
                # Load context config
                context_data = data.get("context", {})
                wc.context = ContextConfig(
                    warn_threshold=context_data.get("warn_threshold", 60),
                    recommend_threshold=context_data.get("recommend_threshold", 75),
                    urgent_threshold=context_data.get("urgent_threshold", 85),
                    trim_threshold_chars=context_data.get("trim_threshold_chars", 500),
                    trim_target_tools=context_data.get("trim_target_tools"),
                    check_interval_seconds=context_data.get("check_interval_seconds", 60),
                )
```

**Step 6: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_config.py::TestContextConfig -v`

Expected: PASS (4 tests)

**Step 7: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: 118 passed

**Step 8: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_config.py && git commit -m "feat(config): add ContextConfig for context management settings"
```

---

## Task 4: Add Context Percentage Parsing

**Files:**
- Modify: `work` (add function)
- Create: `tests/test_context.py`

**Step 1: Write the failing tests**

Create `tests/test_context.py`:

```python
"""Tests for context management functionality."""

import json
import tempfile
from pathlib import Path

import work


class TestParseContextPercentage:
    """Tests for parsing context percentage from Claude session files."""

    def test_parse_from_session_file(self, tmp_path):
        """Should extract context percentage from session metadata."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "metadata", "contextTokens": 50000, "maxContextTokens": 100000}) + "\n"
        )

        result = work.get_context_percentage_from_file(session_file)
        assert result == 50

    def test_returns_none_when_no_metadata(self, tmp_path):
        """Should return None when file has no context metadata."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "user", "message": "hello"}) + "\n"
        )

        result = work.get_context_percentage_from_file(session_file)
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path):
        """Should return None when file doesn't exist."""
        result = work.get_context_percentage_from_file(tmp_path / "nonexistent.jsonl")
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py -v`

Expected: FAIL with "module 'work' has no attribute 'get_context_percentage_from_file'"

**Step 3: Implement get_context_percentage_from_file**

Add to `work`:

```python
def get_context_percentage_from_file(session_file: Path) -> Optional[int]:
    """
    Parse context percentage from a Claude session JSONL file.
    Returns None if file doesn't exist or has no context metadata.
    """
    if not session_file.exists():
        return None

    try:
        # Read file in reverse to find most recent metadata
        with open(session_file, "r") as f:
            lines = f.readlines()

        for line in reversed(lines):
            try:
                data = json.loads(line.strip())
                if "contextTokens" in data and "maxContextTokens" in data:
                    context_tokens = data["contextTokens"]
                    max_tokens = data["maxContextTokens"]
                    if max_tokens > 0:
                        return int((context_tokens / max_tokens) * 100)
            except json.JSONDecodeError:
                continue

        return None
    except Exception:
        return None
```

**Step 4: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_context.py && git commit -m "feat(context): add context percentage parsing from session files"
```

---

## Task 5: Implement Session Trimming Core Logic

**Files:**
- Modify: `work` (add trim functions)
- Modify: `tests/test_context.py`

**Step 1: Write the failing tests**

Add to `tests/test_context.py`:

```python
class TestTrimSession:
    """Tests for session trimming functionality."""

    def test_truncate_content_over_threshold(self):
        """Should truncate content exceeding threshold."""
        content = "x" * 1000
        result = work.truncate_content(content, threshold=500, tool_name="Read", line_num=5, parent_file="/parent.jsonl")

        assert len(result) < len(content)
        assert result.startswith("x" * 500)
        assert "[...truncated" in result
        assert "line 5" in result

    def test_truncate_content_under_threshold(self):
        """Should not truncate content under threshold."""
        content = "x" * 100
        result = work.truncate_content(content, threshold=500, tool_name="Read", line_num=5, parent_file="/parent.jsonl")

        assert result == content

    def test_build_tool_name_mapping(self, tmp_path):
        """Should map tool_use_id to tool_name."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "tool-123", "name": "Read"}
                    ]
                }
            }) + "\n"
        )

        result = work.build_tool_name_mapping(session_file)
        assert result["tool-123"] == "Read"

    def test_trim_session_creates_new_file(self, tmp_path):
        """Should create trimmed session file."""
        # Create a session with a large tool result
        session_file = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "assistant", "sessionId": "orig-123", "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Read"}]}}),
            json.dumps({"type": "user", "sessionId": "orig-123", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "x" * 1000}]}}),
        ]
        session_file.write_text("\n".join(lines) + "\n")

        output_file = tmp_path / "trimmed.jsonl"
        stats = work.trim_session_file(
            input_file=session_file,
            output_file=output_file,
            threshold=500,
            target_tools={"Read"},
        )

        assert output_file.exists()
        assert stats["trimmed_count"] >= 1

        # Verify content was truncated
        with open(output_file) as f:
            for line in f:
                data = json.loads(line)
                if data.get("type") == "user":
                    content = data.get("message", {}).get("content", [])
                    for item in content:
                        if item.get("type") == "tool_result":
                            assert len(str(item.get("content", ""))) < 1000
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py::TestTrimSession -v`

Expected: FAIL with "module 'work' has no attribute 'truncate_content'"

**Step 3: Implement trim functions**

Add to `work`:

```python
def truncate_content(
    content: str,
    threshold: int,
    tool_name: str,
    line_num: int,
    parent_file: str,
) -> str:
    """
    Truncate content if it exceeds threshold.
    Keeps first N chars and adds reference to parent file.
    """
    if len(content) <= threshold:
        return content

    truncated = content[:threshold]
    notice = (
        f"\n\n[...truncated - original was {len(content):,} chars, "
        f"showing first {threshold}. See line {line_num} of {parent_file} for full content]"
    )

    result = truncated + notice
    # Only return truncated if it actually saves space
    if len(result) >= len(content):
        return content
    return result


def build_tool_name_mapping(session_file: Path) -> dict:
    """
    Build mapping of tool_use_id -> tool_name from session file.
    First pass to enable identifying tool results by their tool name.
    """
    tool_map = {}

    with open(session_file, "r") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data.get("type") == "assistant":
                    content = data.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_use":
                                tool_id = item.get("id")
                                tool_name = item.get("name")
                                if tool_id and tool_name:
                                    tool_map[tool_id] = tool_name
            except json.JSONDecodeError:
                continue

    return tool_map


def trim_session_file(
    input_file: Path,
    output_file: Path,
    threshold: int = 500,
    target_tools: set = None,
) -> dict:
    """
    Trim large tool outputs from a Claude session file.
    Returns stats about what was trimmed.
    """
    if target_tools is None:
        target_tools = {"Read", "Bash", "Grep", "Glob"}

    tool_map = build_tool_name_mapping(input_file)
    parent_file = str(input_file.absolute())

    trimmed_count = 0
    original_size = 0
    new_size = 0

    with open(input_file, "r") as infile, open(output_file, "w") as outfile:
        for line_num, line in enumerate(infile, start=1):
            original_size += len(line)

            try:
                data = json.loads(line.strip())

                # Process user messages containing tool results
                if data.get("type") == "user":
                    content = data.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_result":
                                tool_use_id = item.get("tool_use_id")
                                tool_name = tool_map.get(tool_use_id, "Unknown")

                                if tool_name in target_tools:
                                    result_content = item.get("content", "")
                                    if isinstance(result_content, str) and len(result_content) > threshold:
                                        item["content"] = truncate_content(
                                            result_content,
                                            threshold,
                                            tool_name,
                                            line_num,
                                            parent_file,
                                        )
                                        trimmed_count += 1

                new_line = json.dumps(data) + "\n"
                outfile.write(new_line)
                new_size += len(new_line)

            except json.JSONDecodeError:
                outfile.write(line)
                new_size += len(line)

    return {
        "trimmed_count": trimmed_count,
        "original_size": original_size,
        "new_size": new_size,
        "bytes_saved": original_size - new_size,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py::TestTrimSession -v`

Expected: PASS (4 tests)

**Step 5: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: All tests pass

**Step 6: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_context.py && git commit -m "feat(trim): implement session trimming core logic"
```

---

## Task 6: Add --trim CLI Command

**Files:**
- Modify: `work` (add CLI command)
- Modify: `tests/test_context.py`

**Step 1: Write the failing test**

Add to `tests/test_context.py`:

```python
from click.testing import CliRunner


class TestTrimCommand:
    """Tests for the --trim CLI command."""

    def test_trim_command_requires_worker_env(self):
        """Should error when not in worker session."""
        runner = CliRunner()
        result = runner.invoke(work.cli, ["--trim"])

        assert result.exit_code != 0
        assert "worker session" in result.output.lower() or "WORK_WORKER_ID" in result.output
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py::TestTrimCommand -v`

Expected: FAIL with "no such option: --trim"

**Step 3: Add --trim option to CLI**

Find the main CLI group in `work` and add the trim option. Add near other CLI options:

```python
@click.option("--trim", is_flag=True, help="Trim large tool outputs from current session")
```

And add handling in the main function:

```python
def cli(trim, ...):  # Add trim parameter
    # ... existing code ...

    if trim:
        worker_id = os.environ.get("WORK_WORKER_ID")
        if not worker_id:
            click.echo("Error: --trim must be run within a worker session (WORK_WORKER_ID not set)", err=True)
            sys.exit(1)

        return cmd_trim(int(worker_id))


def cmd_trim(worker_id: int) -> None:
    """Handle --trim command."""
    click.echo("Syncing to episodic-memory...")
    subprocess.run(["episodic-memory", "sync"], check=False, capture_output=True)

    # Find current session file
    session_file = find_current_session_file()
    if not session_file:
        click.echo("Error: Could not find current session file", err=True)
        sys.exit(1)

    # Create trimmed output file
    output_file = session_file.with_suffix(".trimmed.jsonl")

    work_config = load_work_config()
    stats = trim_session_file(
        input_file=session_file,
        output_file=output_file,
        threshold=work_config.context.trim_threshold_chars,
        target_tools=set(work_config.context.trim_target_tools),
    )

    click.echo(f"Trimmed {stats['trimmed_count']} tool outputs")
    click.echo(f"Saved {stats['bytes_saved']:,} bytes ({stats['bytes_saved'] * 100 // stats['original_size']}%)")

    # Inject trim metadata
    inject_trim_metadata(output_file, session_file, stats)

    # Generate new session ID and update file
    new_session_id = str(uuid.uuid4())
    update_session_id_in_file(output_file, new_session_id)

    # Move trimmed file to proper location
    final_path = session_file.parent / f"{new_session_id}.jsonl"
    output_file.rename(final_path)

    click.echo(f"Resume with: claude --resume {new_session_id}")
```

**Step 4: Add helper functions**

```python
import uuid


def find_current_session_file() -> Optional[Path]:
    """Find the current Claude session file based on environment."""
    # Claude stores sessions in ~/.claude/projects/{encoded_path}/{session_id}.jsonl
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    # Find most recently modified .jsonl file
    jsonl_files = list(claude_dir.rglob("*.jsonl"))
    if not jsonl_files:
        return None

    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


def inject_trim_metadata(output_file: Path, parent_file: Path, stats: dict) -> None:
    """Add trim metadata to first line of session file."""
    with open(output_file, "r") as f:
        lines = f.readlines()

    if not lines:
        return

    first_line_data = json.loads(lines[0])
    first_line_data["trim_metadata"] = {
        "parent_file": str(parent_file.absolute()),
        "trimmed_at": datetime.now().isoformat(),
        "threshold": stats.get("threshold", 500),
        "trimmed_count": stats["trimmed_count"],
        "bytes_saved": stats["bytes_saved"],
    }
    lines[0] = json.dumps(first_line_data) + "\n"

    with open(output_file, "w") as f:
        f.writelines(lines)


def update_session_id_in_file(file_path: Path, new_session_id: str) -> None:
    """Update sessionId in all lines of a session file."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    updated_lines = []
    for line in lines:
        try:
            data = json.loads(line)
            if "sessionId" in data:
                data["sessionId"] = new_session_id
            updated_lines.append(json.dumps(data) + "\n")
        except json.JSONDecodeError:
            updated_lines.append(line)

    with open(file_path, "w") as f:
        f.writelines(updated_lines)
```

**Step 5: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py::TestTrimCommand -v`

Expected: PASS

**Step 6: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: All tests pass

**Step 7: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_context.py && git commit -m "feat(cli): add --trim command for session trimming"
```

---

## Task 7: Create /trim Skill

**Files:**
- Create: `skills/trim/skill.md`

**Step 1: Create skill directory**

```bash
cd ~/.worktrees/work/context-management && mkdir -p skills/trim
```

**Step 2: Write skill file**

Create `skills/trim/skill.md`:

```markdown
---
name: trim
description: Trim large tool outputs to free context space
---

To free context space, run:

```bash
./work --trim
```

This will:
1. Sync current session to episodic-memory (preserve full content)
2. Find tool outputs over 500 characters (configurable in .work.toml)
3. Truncate them, keeping first 500 chars + reference to original
4. Create new session file with trim metadata
5. Output resume command for the trimmed session

**Typical savings:** 30-50% on first trim.

**After trimming:**
- Run `claude --resume <session-id>` with the ID shown
- If you need full content of a truncated result, re-run the tool or search episodic-memory

**If trimming doesn't free meaningful space (<10% saved), use `/rollover` instead.**

**Configuration** (`.work.toml`):
```toml
[context]
trim_threshold_chars = 500           # Characters to keep before truncating
trim_target_tools = ["Read", "Bash", "Grep", "Glob"]  # Tools to trim
```
```

**Step 3: Commit**

```bash
cd ~/.worktrees/work/context-management && git add skills/trim && git commit -m "feat(skills): add /trim skill"
```

---

## Task 8: Add --rollover CLI Command

**Files:**
- Modify: `work` (add CLI command)
- Modify: `tests/test_context.py`

**Step 1: Write the failing test**

Add to `tests/test_context.py`:

```python
class TestRolloverCommand:
    """Tests for the --rollover CLI command."""

    def test_rollover_command_requires_worker_env(self):
        """Should error when not in worker session."""
        runner = CliRunner()
        result = runner.invoke(work.cli, ["--rollover", "--summary-file", "/tmp/test.txt"])

        assert result.exit_code != 0
        assert "worker session" in result.output.lower() or "WORK_WORKER_ID" in result.output

    def test_rollover_command_requires_summary_file(self):
        """Should error when summary file not provided."""
        runner = CliRunner(env={"WORK_WORKER_ID": "1", "WORK_DB_PATH": "/tmp/test.db"})
        result = runner.invoke(work.cli, ["--rollover"])

        # Should error about missing summary file
        assert result.exit_code != 0
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py::TestRolloverCommand -v`

Expected: FAIL with "no such option: --rollover"

**Step 3: Add --rollover option to CLI**

Add to CLI options:

```python
@click.option("--rollover", is_flag=True, help="Start fresh session with handoff summary")
@click.option("--summary-file", type=click.Path(exists=True), help="Path to summary file for rollover")
```

Add to main function:

```python
def cli(rollover, summary_file, ...):  # Add parameters
    # ... existing code ...

    if rollover:
        worker_id = os.environ.get("WORK_WORKER_ID")
        if not worker_id:
            click.echo("Error: --rollover must be run within a worker session (WORK_WORKER_ID not set)", err=True)
            sys.exit(1)

        if not summary_file:
            click.echo("Error: --rollover requires --summary-file", err=True)
            sys.exit(1)

        return cmd_rollover(int(worker_id), Path(summary_file))


def cmd_rollover(worker_id: int, summary_file: Path) -> None:
    """Handle --rollover command."""
    summary = summary_file.read_text().strip()

    click.echo("Syncing to episodic-memory...")
    subprocess.run(["episodic-memory", "sync"], check=False, capture_output=True)

    db_path = Path(os.environ.get("WORK_DB_PATH", config.db_path))

    with get_db(db_path) as db:
        # Get worker info
        cursor = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,))
        worker_row = cursor.fetchone()
        if not worker_row:
            click.echo(f"Error: Worker {worker_id} not found", err=True)
            sys.exit(1)

        # Get current session info
        session_file = find_current_session_file()
        context_pct = get_context_percentage_from_file(session_file) if session_file else None
        current_session_num = get_current_session_number(db, worker_id)

        # End current session
        if current_session_num > 0:
            cursor = db.execute(
                "SELECT id FROM sessions WHERE worker_id = ? AND session_number = ?",
                (worker_id, current_session_num)
            )
            session_row = cursor.fetchone()
            if session_row:
                end_session(db, session_row[0], "rollover", context_pct, summary)

        # Create new session record
        new_session_num = current_session_num + 1
        create_session(db, worker_id, new_session_num)

        # Build continuation prompt
        issue_ref = f"#{worker_row[3]}"  # issue_number column
        worktree_path = worker_row[5]  # worktree_path column

        prompt = build_continuation_prompt(
            issue_ref=issue_ref,
            summary=summary,
            session_number=new_session_num,
            parent_session_file=session_file,
            context_at_rollover=context_pct or 0,
            worker_id=worker_id,
        )

        # Write prompt to temp file
        prompt_file = Path(f"/tmp/work-continuation-{worker_id}.md")
        prompt_file.write_text(prompt)

        click.echo(f"Starting session #{new_session_num}...")
        click.echo(f"Prompt saved to: {prompt_file}")
        click.echo(f"Run: claude --prompt-file {prompt_file}")


def build_continuation_prompt(
    issue_ref: str,
    summary: str,
    session_number: int,
    parent_session_file: Optional[Path],
    context_at_rollover: int,
    worker_id: int,
) -> str:
    """Build the continuation prompt for a rolled-over session."""
    parent_ref = str(parent_session_file) if parent_session_file else "unknown"

    return f"""## Session Continuation

This is session #{session_number} for {issue_ref}.
Previous session rolled over at {context_at_rollover}% context to preserve quality.

### Handoff Summary

{summary}

### Retrieving Details

The full previous session is indexed in episodic-memory. For details not in
the summary above, search with:

```
mcp__episodic-memory__search with query: "what you need to find"
```

Example queries:
- "decision about [topic]"
- "error in [component]"
- "changes to [filename]"

### Lineage

Parent session: {parent_ref}
Worker ID: {worker_id}

---

Continue from the handoff summary. Your next step is in "Immediate Next Steps" above.
"""
```

**Step 4: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_context.py::TestRolloverCommand -v`

Expected: PASS (2 tests)

**Step 5: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: All tests pass

**Step 6: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_context.py && git commit -m "feat(cli): add --rollover command for session continuation"
```

---

## Task 9: Create /rollover Skill

**Files:**
- Create: `skills/rollover/skill.md`

**Step 1: Create skill directory**

```bash
cd ~/.worktrees/work/context-management && mkdir -p skills/rollover
```

**Step 2: Write skill file**

Create `skills/rollover/skill.md`:

```markdown
---
name: rollover
description: Start fresh session when context is high, preserving continuity via episodic-memory
---

You've decided to rollover to a fresh session. This preserves your full session
in episodic-memory while starting clean.

## Step 1: Generate Handoff Summary

Write a BRIEF handoff summary (aim for ~500 words max). Focus on state, not history:

```
### Current Task
[Issue/goal and current status in 1-2 sentences]

### Key Decisions
- [Decision]: [rationale] (1 line each, max 5)

### Modified Files
- [file]: [what changed] (1 line each)

### Immediate Next Steps
1. [Next action to take]
2. [Following action]

### Critical Context
[Anything the next session MUST know - blockers, gotchas, important findings]
```

## Step 2: Execute Rollover

Save your summary and run the rollover command:

```bash
cat > /tmp/rollover-summary.txt << 'EOF'
[paste your summary here]
EOF

./work --rollover --summary-file /tmp/rollover-summary.txt
```

This will:
1. Sync current session to episodic-memory (full content preserved)
2. Record session end in database with lineage
3. Generate continuation prompt for new session
4. Output the command to start the new session

## Step 3: Start New Session

Run the command output by the rollover (usually):
```bash
claude --prompt-file /tmp/work-continuation-{worker_id}.md
```

## Step 4: In the New Session

Your summary will be injected automatically. For details NOT in the summary,
use episodic-memory to search the full parent session:

```
mcp__episodic-memory__search with query: "specific thing you need"
```

The parent session is fully indexed - nothing is lost, just a search away.
```

**Step 3: Commit**

```bash
cd ~/.worktrees/work/context-management && git add skills/rollover && git commit -m "feat(skills): add /rollover skill"
```

---

## Task 10: Add Context Warnings to Hook

**Files:**
- Modify: `hooks/work-stage-detector.sh`
- Modify: `tests/test_hooks.py`

**Step 1: Update the hook**

Add to `hooks/work-stage-detector.sh` (after existing stage detection logic):

```bash
# =============================================================================
# Context Monitoring
# =============================================================================

get_context_percentage() {
    # Source status line script if available for context percentage
    local statusline_script="${HOME}/.claude/scripts/work-statusline.sh"
    if [[ -f "$statusline_script" ]]; then
        source "$statusline_script" 2>/dev/null
        echo "${CONTEXT_PCT:-}"
    fi
}

inject_context_reminder() {
    local pct="$1"
    local config_file

    # Load thresholds from .work.toml if available
    local warn_threshold=60
    local recommend_threshold=75
    local urgent_threshold=85

    config_file="$(git rev-parse --show-toplevel 2>/dev/null)/.work.toml"
    if [[ -f "$config_file" ]]; then
        warn_threshold=$(grep -E '^warn_threshold\s*=' "$config_file" 2>/dev/null | sed 's/.*=\s*//' | tr -d ' ' || echo 60)
        recommend_threshold=$(grep -E '^recommend_threshold\s*=' "$config_file" 2>/dev/null | sed 's/.*=\s*//' | tr -d ' ' || echo 75)
        urgent_threshold=$(grep -E '^urgent_threshold\s*=' "$config_file" 2>/dev/null | sed 's/.*=\s*//' | tr -d ' ' || echo 85)
    fi

    if [[ $pct -ge $urgent_threshold ]]; then
        echo "<system-reminder>Context at ${pct}%. Use /trim or /rollover now to avoid lossy auto-compaction at 95%.</system-reminder>"
    elif [[ $pct -ge $recommend_threshold ]]; then
        echo "<system-reminder>Context at ${pct}%. Recommend /trim soon, or /rollover if trim isn't helping.</system-reminder>"
    elif [[ $pct -ge $warn_threshold ]]; then
        echo "<system-reminder>Context at ${pct}%. Consider /trim if response quality feels degraded.</system-reminder>"
    fi
}

# Rate-limit context checks (every 60 seconds)
check_context_with_rate_limit() {
    local check_file="/tmp/work-context-check-$$"
    local now
    local last_check
    local check_interval=60

    now=$(date +%s)
    last_check=$(cat "$check_file" 2>/dev/null || echo 0)

    if (( now - last_check > check_interval )); then
        echo "$now" > "$check_file"
        local context_pct
        context_pct=$(get_context_percentage)
        if [[ -n "$context_pct" && "$context_pct" =~ ^[0-9]+$ ]]; then
            inject_context_reminder "$context_pct"
        fi
    fi
}

# Only run context check if we're in a worker session
if [[ -n "${WORK_WORKER_ID:-}" ]]; then
    check_context_with_rate_limit
fi
```

**Step 2: Run shellcheck**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_hooks.py -v`

Expected: All hook tests pass (shellcheck, shebang, executable)

**Step 3: Commit**

```bash
cd ~/.worktrees/work/context-management && git add hooks/work-stage-detector.sh && git commit -m "feat(hooks): add context monitoring and warnings"
```

---

## Task 11: Add Context Instructions to Worker Prompt

**Files:**
- Modify: `work` (generate_prompt function)
- Modify: `tests/test_prompt.py`

**Step 1: Write the failing test**

Add to `tests/test_prompt.py`:

```python
class TestContextManagementInPrompt:
    """Tests for context management instructions in worker prompt."""

    def test_prompt_includes_context_management(self):
        """Should include context management section."""
        prompt = work.generate_prompt(
            task_ref="#42",
            gh_cli="gh",
            worker_guidelines="",
        )

        assert "Context Management" in prompt
        assert "/trim" in prompt
        assert "/rollover" in prompt

    def test_prompt_mentions_thresholds(self):
        """Should mention context thresholds."""
        prompt = work.generate_prompt(
            task_ref="#42",
            gh_cli="gh",
            worker_guidelines="",
        )

        assert "60%" in prompt or "60" in prompt
        assert "auto-compaction" in prompt.lower() or "95%" in prompt
```

**Step 2: Run test to verify it fails**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_prompt.py::TestContextManagementInPrompt -v`

Expected: FAIL (context management not in prompt yet)

**Step 3: Add context management instructions**

Add constant to `work`:

```python
CONTEXT_MANAGEMENT_INSTRUCTIONS = """
## Context Management

Your context window has limited capacity. Quality degrades around 60% usage,
and auto-compaction (lossy) triggers at 95%.

### Monitoring
- Status line shows current context percentage
- You'll receive system reminders at 60%, 75%, and 85%

### Actions

**At 60%+** - Consider `/trim` if you notice degraded responses:
```
/trim
```
This removes large old tool outputs while preserving decisions and recent work.
Can free 30-50% of context. Use multiple times if needed.

**At 75%+ or trim ineffective** - Use `/rollover`:
```
/rollover
```
This starts a fresh session with your handoff summary. Full context is
preserved in episodic-memory for retrieval.

### Priority Order
1. `/trim` - Least disruptive, stay in session
2. `/rollover` - Clean handoff, fresh context
3. Auto-compaction - Last resort (lossy, avoid if possible)
"""
```

**Step 4: Include in generate_prompt**

Find `generate_prompt` function and add `CONTEXT_MANAGEMENT_INSTRUCTIONS` to the prompt template where appropriate (after guidelines, before task steps).

**Step 5: Run test to verify it passes**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/test_prompt.py::TestContextManagementInPrompt -v`

Expected: PASS (2 tests)

**Step 6: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: All tests pass

**Step 7: Commit**

```bash
cd ~/.worktrees/work/context-management && git add work tests/test_prompt.py && git commit -m "feat(prompt): add context management instructions to worker prompt"
```

---

## Task 12: Final Integration Test and Documentation

**Files:**
- Update: `docs/plans/2026-01-18-context-management-design.md` (mark complete)
- Update: `CLAUDE.md` (document new features)

**Step 1: Run full test suite**

Run: `cd ~/.worktrees/work/context-management && uv run --extra test pytest tests/ -v`

Expected: All tests pass

**Step 2: Update CLAUDE.md**

Add to the CLAUDE.md documentation:

```markdown
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
```

**Step 3: Commit documentation**

```bash
cd ~/.worktrees/work/context-management && git add CLAUDE.md && git commit -m "docs: document context management features"
```

**Step 4: Create PR or merge**

Use `superpowers:finishing-a-development-branch` skill to complete the work.

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Sessions table schema | 3 |
| 2 | Session CRUD functions | 4 |
| 3 | ContextConfig | 4 |
| 4 | Context percentage parsing | 3 |
| 5 | Session trimming core | 4 |
| 6 | --trim CLI command | 1 |
| 7 | /trim skill | - |
| 8 | --rollover CLI command | 2 |
| 9 | /rollover skill | - |
| 10 | Hook context warnings | - |
| 11 | Worker prompt additions | 2 |
| 12 | Integration & docs | - |

**Total new tests:** ~23
**Estimated commits:** 12
