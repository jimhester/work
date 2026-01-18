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

        # Verify content was truncated
        with open(output_file) as f:
            for line in f:
                data = json.loads(line)
                if data.get("type") == "user":
                    content = data.get("message", {}).get("content", [])
                    for item in content:
                        if item.get("type") == "tool_result":
                            assert len(str(item.get("content", ""))) < 1000
