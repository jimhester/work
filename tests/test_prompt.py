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

        # Check key workflow steps are present
        assert "**Plan**" in prompt
        assert "**Implement**" in prompt
        assert "**Self-review**" in prompt
        assert "**Create PR**" in prompt
        assert "**CI loop**" in prompt
        assert "**Merge**" in prompt
        assert "**Follow-up**" in prompt
        assert "**Done**" in prompt

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
        assert "required before PR" in prompt

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

    def test_follow_up_issues_step(self, monkeypatch):
        """Should include follow-up issues step."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh")

        assert "**Follow-up**" in prompt
        assert "TODOs" in prompt or "follow-up" in prompt.lower()

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
        assert "## Workflow" in prompt

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


class TestTargetRepoSupport:
    """Tests for fork/target repo support in generate_prompt."""

    def test_no_repo_flag_without_target_repo(self, monkeypatch):
        """Should not include --repo flag when target_repo is None."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh", target_repo=None)

        # Commands should not have --repo flag
        assert "gh pr create --repo" not in prompt
        assert "gh pr checks --watch --repo" not in prompt

    def test_includes_repo_flag_with_target_repo(self, monkeypatch):
        """Should include --repo flag when target_repo is specified."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "gh", target_repo="jimhester/vroom")

        # Commands should have --repo flag
        assert "gh pr create --repo jimhester/vroom" in prompt
        assert "gh pr checks --watch --repo jimhester/vroom" in prompt
        assert "gh pr merge --squash --repo jimhester/vroom" in prompt

    def test_repo_flag_with_ghe_cli(self, monkeypatch):
        """Should work with ghe CLI as well."""
        monkeypatch.setattr(work, "load_work_config", lambda: work.WorkConfig())

        prompt = work.generate_prompt("Task", "ghe", target_repo="team/project")

        assert "ghe pr create --repo team/project" in prompt
        assert "ghe pr checks --watch --repo team/project" in prompt


class TestDetectGhCli:
    """Tests for detect_gh_cli function."""

    def test_detects_ghe_from_url(self, monkeypatch):
        """Should return ghe when URL contains github.netflix.net."""
        # Mock subprocess to avoid actual git calls
        monkeypatch.setattr(
            work.subprocess, "run",
            lambda *args, **kwargs: type("Result", (), {"stdout": "git@github.com:user/repo.git", "returncode": 0})()
        )

        result = work.detect_gh_cli("https://github.netflix.net/team/project/issues/42")
        assert result == "ghe"

    def test_detects_gh_from_public_github_url(self, monkeypatch):
        """Should return gh for public GitHub URLs."""
        # Mock subprocess to return non-netflix remote
        monkeypatch.setattr(
            work.subprocess, "run",
            lambda *args, **kwargs: type("Result", (), {"stdout": "git@github.com:user/repo.git", "returncode": 0})()
        )

        result = work.detect_gh_cli("https://github.com/jimhester/vroom/issues/6")
        assert result == "gh"

    def test_falls_back_to_origin_when_no_url(self, mocker):
        """Should check origin remote when no URL provided."""
        mock_run = mocker.patch.object(work.subprocess, "run")
        mock_run.return_value.stdout = "git@github.netflix.net:team/repo.git"
        mock_run.return_value.returncode = 0

        result = work.detect_gh_cli()
        assert result == "ghe"


class TestFetchFunctionsWithRepo:
    """Tests for fetch functions with repo parameter."""

    def test_fetch_issue_title_builds_correct_command_without_repo(self, mocker):
        """Should not include --repo when repo is None."""
        mock_run = mocker.patch.object(work.subprocess, "run")
        mock_run.return_value.stdout = '{"title": "Test"}'
        mock_run.return_value.returncode = 0

        work.fetch_issue_title(42, "gh", repo=None)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "issue", "view", "42", "--json", "title"]

    def test_fetch_issue_title_builds_correct_command_with_repo(self, mocker):
        """Should include --repo when repo is specified."""
        mock_run = mocker.patch.object(work.subprocess, "run")
        mock_run.return_value.stdout = '{"title": "Test"}'
        mock_run.return_value.returncode = 0

        work.fetch_issue_title(42, "gh", repo="jimhester/vroom")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "issue", "view", "42", "--json", "title", "--repo", "jimhester/vroom"]

    def test_fetch_pr_branch_builds_correct_command_with_repo(self, mocker):
        """Should include --repo when repo is specified."""
        mock_run = mocker.patch.object(work.subprocess, "run")
        mock_run.return_value.stdout = '{"headRefName": "feature-branch"}'
        mock_run.return_value.returncode = 0

        work.fetch_pr_branch(123, "gh", repo="owner/repo")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "pr", "view", "123", "--json", "headRefName", "--repo", "owner/repo"]
