"""Tests for prompt generation."""

import pytest

from conftest import work


class TestGeneratePrompt:
    """Tests for generate_prompt function."""

    def test_basic_prompt_structure(self, monkeypatch):
        """Prompt should contain key sections."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Fix bug #42", "gh")

        # Check task reference is included
        assert "Fix bug #42" in prompt

        # Check key phases are present
        assert "Phase 1: Implementation" in prompt
        assert "Phase 2: Pull Request" in prompt
        assert "Phase 3: CI & Review Loop" in prompt
        assert "Phase 4: Merge" in prompt
        assert "Phase 5: Follow-up Issues" in prompt
        assert "Phase 6: Completion Summary" in prompt

        # Check important instructions
        assert "CLAUDE.md" in prompt
        assert "work --review" in prompt
        assert "work --done" in prompt

    def test_uses_gh_cli_parameter(self, monkeypatch):
        """Should use the specified GitHub CLI."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt_gh = work.generate_prompt("Task", "gh")
        prompt_ghe = work.generate_prompt("Task", "ghe")

        assert "gh pr create" in prompt_gh
        assert "ghe pr create" in prompt_ghe
        assert "gh pr checks" in prompt_gh
        assert "ghe pr checks" in prompt_ghe

    def test_jira_instructions_when_jira_key_provided(self, monkeypatch):
        """Should include JIRA MCP instructions when jira_key is provided."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh", jira_key="AIE-123")

        assert "JIRA" in prompt
        assert "AIE-123" in prompt
        assert "getJiraIssue" in prompt
        assert "Atlassian MCP" in prompt

    def test_no_jira_instructions_without_jira_key(self, monkeypatch):
        """Should not include JIRA instructions when no jira_key."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("GitHub issue #42", "gh")

        assert "getJiraIssue" not in prompt
        # JIRA might appear in general text, so check for specific instruction
        assert "Atlassian MCP" not in prompt

    def test_includes_worker_guidelines(self, monkeypatch):
        """Should include worker guidelines from config."""
        config = work.WorkConfig(
            worker_guidelines="Always run linter before committing"
        )
        monkeypatch.setattr(work, "load_work_config", lambda: config)

        prompt = work.generate_prompt("Task", "gh")

        assert "Always run linter before committing" in prompt

    def test_no_extra_whitespace_without_guidelines(self, monkeypatch):
        """Should not have trailing whitespace when no guidelines."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        # Guidelines section should not add extra blank lines at end
        assert not prompt.endswith("\n\n\n")

    def test_self_review_required_before_pr(self, monkeypatch):
        """Should emphasize self-review is required before PR."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        assert "work --review" in prompt
        assert "REQUIRED" in prompt

    def test_pre_merge_review_mentioned(self, monkeypatch):
        """Should mention pre-merge review requirement."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        assert "--pre-merge" in prompt

    def test_never_merge_without_approval(self, monkeypatch):
        """Should emphasize not to merge without approval."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        assert "NEVER merge without" in prompt
        assert "approving review" in prompt.lower()

    def test_follow_up_issues_required(self, monkeypatch):
        """Should emphasize follow-up issues phase is required."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        assert "Follow-up Issues (REQUIRED)" in prompt

    def test_messages_mentioned(self, monkeypatch):
        """Should mention the messages feature."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        assert "work --messages" in prompt


class TestGeneratePromptEdgeCases:
    """Edge case tests for generate_prompt."""

    def test_empty_task_ref(self, monkeypatch):
        """Should handle empty task reference."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("", "gh")

        # Should still generate valid prompt structure
        assert "Phase 1: Implementation" in prompt

    def test_special_characters_in_task_ref(self, monkeypatch):
        """Should handle special characters in task reference."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Fix: issue with <brackets> & 'quotes'", "gh")

        assert "Fix: issue with <brackets> & 'quotes'" in prompt

    def test_multiline_worker_guidelines(self, monkeypatch):
        """Should handle multiline worker guidelines."""
        config = work.WorkConfig(
            worker_guidelines="""Line 1
Line 2
Line 3"""
        )
        monkeypatch.setattr(work, "load_work_config", lambda: config)

        prompt = work.generate_prompt("Task", "gh")

        assert "Line 1" in prompt
        assert "Line 2" in prompt
        assert "Line 3" in prompt

    def test_whitespace_only_guidelines_ignored(self, monkeypatch):
        """Should ignore guidelines that are only whitespace."""
        config = work.WorkConfig(worker_guidelines="   \n\t  ")
        monkeypatch.setattr(work, "load_work_config", lambda: config)

        prompt = work.generate_prompt("Task", "gh")

        # Should not have extra blank section
        lines = prompt.split("\n")
        # No line should be just the whitespace guidelines
        assert "   \n\t  " not in prompt
