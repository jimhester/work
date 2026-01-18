"""Tests for configuration loading."""

import pytest

from conftest import work


class TestWorkConfigDefaults:
    """Tests for WorkConfig default values."""

    def test_default_values(self):
        """WorkConfig should have sensible defaults."""
        config = work.WorkConfig()
        assert config.worker_guidelines == ""
        assert config.review_guidelines == ""
        assert config.review_strictness == "normal"
        assert config.require_pre_merge_review is True

    def test_default_exclude_patterns(self):
        """Should have default exclude patterns for lock files."""
        config = work.WorkConfig()
        assert "*.lock" in config.review_exclude_patterns
        assert "package-lock.json" in config.review_exclude_patterns
        assert "yarn.lock" in config.review_exclude_patterns
        assert "Cargo.lock" in config.review_exclude_patterns

    def test_custom_exclude_patterns(self):
        """Custom exclude patterns should override defaults."""
        config = work.WorkConfig(review_exclude_patterns=["custom.lock"])
        assert config.review_exclude_patterns == ["custom.lock"]
        assert "*.lock" not in config.review_exclude_patterns


class TestLoadWorkConfig:
    """Tests for load_work_config function."""

    def test_load_from_work_toml(self, tmp_path, monkeypatch):
        """Should load config from .work.toml."""
        config_file = tmp_path / ".work.toml"
        config_file.write_text('''
worker_guidelines = "Always write tests first"
review_guidelines = "Check for SQL injection"
review_strictness = "strict"
require_pre_merge_review = false
''')
        # Mock get_repo_root to return our temp directory
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.worker_guidelines == "Always write tests first"
        assert config.review_guidelines == "Check for SQL injection"
        assert config.review_strictness == "strict"
        assert config.require_pre_merge_review is False

    def test_load_from_work_toml_without_dot(self, tmp_path, monkeypatch):
        """Should also check work.toml (without leading dot)."""
        config_file = tmp_path / "work.toml"
        config_file.write_text('worker_guidelines = "From work.toml"')
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.worker_guidelines == "From work.toml"

    def test_dot_work_toml_takes_precedence(self, tmp_path, monkeypatch):
        """Should prefer .work.toml over work.toml."""
        (tmp_path / ".work.toml").write_text('worker_guidelines = "From .work.toml"')
        (tmp_path / "work.toml").write_text('worker_guidelines = "From work.toml"')
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.worker_guidelines == "From .work.toml"

    def test_returns_defaults_when_no_config(self, tmp_path, monkeypatch):
        """Should return defaults when no config file exists."""
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.worker_guidelines == ""
        assert config.review_strictness == "normal"

    def test_returns_defaults_when_no_repo_root(self, monkeypatch):
        """Should return defaults when not in a git repo."""
        monkeypatch.setattr(work, "get_repo_root", lambda: None)

        config = work.load_work_config()

        assert config.worker_guidelines == ""

    def test_partial_config(self, tmp_path, monkeypatch):
        """Should use defaults for missing fields."""
        config_file = tmp_path / ".work.toml"
        config_file.write_text('worker_guidelines = "Only this is set"')
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.worker_guidelines == "Only this is set"
        assert config.review_guidelines == ""  # default
        assert config.review_strictness == "normal"  # default

    def test_custom_exclude_patterns_in_file(self, tmp_path, monkeypatch):
        """Should load custom exclude patterns from config."""
        config_file = tmp_path / ".work.toml"
        config_file.write_text('''
review_exclude_patterns = ["*.generated.ts", "vendor/*"]
''')
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.review_exclude_patterns == ["*.generated.ts", "vendor/*"]

    def test_invalid_toml_returns_defaults(self, tmp_path, monkeypatch, capsys):
        """Should return defaults and warn on invalid TOML."""
        config_file = tmp_path / ".work.toml"
        config_file.write_text("this is not valid { toml [")
        monkeypatch.setattr(work, "get_repo_root", lambda: tmp_path)

        config = work.load_work_config()

        assert config.worker_guidelines == ""  # defaults
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "Failed to parse" in captured.err


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
