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
