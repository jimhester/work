"""Tests for context management functionality."""

import json
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
        # Verify return dict uses correct keys per spec
        assert "original_chars" in stats
        assert "trimmed_chars" in stats
        assert "bytes_saved" not in stats

        # Verify content was truncated (skip first line which is metadata)
        with open(output_file) as f:
            lines = f.readlines()
            for line in lines[1:]:  # Skip trim_metadata line
                data = json.loads(line)
                if data.get("type") == "user":
                    content = data.get("message", {}).get("content", [])
                    for item in content:
                        if item.get("type") == "tool_result":
                            assert len(str(item.get("content", ""))) < 1000

    def test_trim_session_writes_metadata_first_line(self, tmp_path):
        """Should write trim_metadata as the first line of output file."""
        session_file = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Read"}]}}),
            json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "x" * 1000}]}}),
        ]
        session_file.write_text("\n".join(lines) + "\n")

        output_file = tmp_path / "trimmed.jsonl"
        work.trim_session_file(
            input_file=session_file,
            output_file=output_file,
            threshold=500,
            target_tools={"Read"},
        )

        # Read first line and verify it's trim_metadata
        with open(output_file) as f:
            first_line = f.readline()
            metadata = json.loads(first_line)

        assert "trim_metadata" in metadata
        tm = metadata["trim_metadata"]
        assert "parent_file" in tm
        assert str(session_file.absolute()) in tm["parent_file"]
        assert "trimmed_at" in tm
        assert "threshold" in tm
        assert tm["threshold"] == 500
        assert "trimmed_count" in tm
        assert tm["trimmed_count"] >= 1


class TestTrimCommand:
    """Tests for the --trim CLI command."""

    def test_trim_command_requires_worker_env(self):
        """Should error when WORK_WORKER_ID is not set."""
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(work.cli, ["--trim"], env={"WORK_WORKER_ID": ""})
        assert result.exit_code != 0
        assert "worker session" in result.output.lower() or "WORK_WORKER_ID" in result.output


class TestRolloverCommand:
    """Tests for the --rollover CLI command."""

    def test_rollover_command_requires_worker_env(self, tmp_path):
        """Should error when WORK_WORKER_ID is not set."""
        from click.testing import CliRunner

        # Create a summary file
        summary_file = tmp_path / "summary.txt"
        summary_file.write_text("Test summary")

        runner = CliRunner()
        result = runner.invoke(
            work.cli,
            ["--rollover", "--summary-file", str(summary_file)],
            env={"WORK_WORKER_ID": ""}
        )
        assert result.exit_code != 0
        assert "worker session" in result.output.lower() or "WORK_WORKER_ID" in result.output

    def test_rollover_command_requires_summary_file(self):
        """Should error when --summary-file is not provided."""
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            work.cli,
            ["--rollover"],
            env={"WORK_WORKER_ID": "123"}
        )
        assert result.exit_code != 0
        assert "summary-file" in result.output.lower() or "required" in result.output.lower()


class TestBuildContinuationPrompt:
    """Tests for build_continuation_prompt function."""

    def test_builds_correct_markdown_format(self):
        """Should build prompt with correct markdown structure."""
        result = work.build_continuation_prompt(
            session_number=3,
            issue_ref="issue #42",
            context_pct=85,
            summary="Fixed the bug and added tests",
            parent_session_path="/path/to/session.jsonl",
            worker_id="123"
        )

        assert "## Session Continuation" in result
        assert "session #3" in result
        assert "issue #42" in result
        assert "85%" in result
        assert "### Handoff Summary" in result
        assert "Fixed the bug and added tests" in result
        assert "### Retrieving Details" in result
        assert "episodic-memory" in result
        assert "### Lineage" in result
        assert "/path/to/session.jsonl" in result
        assert "123" in result
