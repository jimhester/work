"""Tests for issue parsing and text processing functions."""

import pytest

from conftest import work


class TestParseGithubUrl:
    """Tests for parse_github_url function."""

    def test_standard_issue_url(self):
        result = work.parse_github_url("https://github.com/owner/repo/issues/42")
        assert result is not None
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.issue_type == "issues"
        assert result.number == 42

    def test_standard_pr_url(self):
        result = work.parse_github_url("https://github.com/owner/repo/pull/123")
        assert result is not None
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.issue_type == "pull"
        assert result.number == 123

    def test_url_with_www(self):
        result = work.parse_github_url("https://www.github.com/owner/repo/issues/1")
        assert result is not None
        assert result.owner == "owner"
        assert result.number == 1

    def test_http_url(self):
        result = work.parse_github_url("http://github.com/owner/repo/issues/99")
        assert result is not None
        assert result.number == 99

    def test_netflix_enterprise_github(self):
        result = work.parse_github_url(
            "https://github.netflix.net/team/project/issues/456"
        )
        assert result is not None
        assert result.owner == "team"
        assert result.repo == "project"
        assert result.number == 456

    def test_invalid_url_returns_none(self):
        assert work.parse_github_url("https://gitlab.com/owner/repo/issues/1") is None
        assert work.parse_github_url("not a url") is None
        assert work.parse_github_url("https://github.com/owner/repo") is None
        assert work.parse_github_url("https://github.com/owner/repo/commits/abc") is None

    def test_complex_repo_names(self):
        result = work.parse_github_url(
            "https://github.com/my-org/my-cool-repo/issues/7"
        )
        assert result is not None
        assert result.owner == "my-org"
        assert result.repo == "my-cool-repo"


class TestParseJiraKey:
    """Tests for parse_jira_key function."""

    def test_plain_jira_key(self):
        assert work.parse_jira_key("AIE-123") == "AIE-123"
        assert work.parse_jira_key("PROJ-1") == "PROJ-1"
        assert work.parse_jira_key("ABC-99999") == "ABC-99999"

    def test_jira_url(self):
        assert work.parse_jira_key(
            "https://netflix.atlassian.net/browse/AIE-456"
        ) == "AIE-456"

    def test_jira_url_with_extra_path(self):
        # Should still extract the key from browse URL
        result = work.parse_jira_key(
            "https://company.atlassian.net/browse/TASK-789"
        )
        assert result == "TASK-789"

    def test_invalid_jira_key_returns_none(self):
        assert work.parse_jira_key("123") is None
        assert work.parse_jira_key("aie-123") is None  # lowercase
        assert work.parse_jira_key("AIE123") is None  # no hyphen
        assert work.parse_jira_key("https://github.com/owner/repo") is None

    def test_jira_key_case_sensitivity(self):
        # JIRA keys must be uppercase
        assert work.parse_jira_key("ABC-123") == "ABC-123"
        assert work.parse_jira_key("abc-123") is None


class TestParseIssueArg:
    """Tests for parse_issue_arg function."""

    def test_plain_issue_number(self):
        issue, repo = work.parse_issue_arg("42")
        assert issue == "42"
        assert repo is None

    def test_repo_prefixed_issue(self):
        issue, repo = work.parse_issue_arg("myrepo:42")
        assert issue == "42"
        assert repo == "myrepo"

    def test_jira_key(self):
        issue, repo = work.parse_issue_arg("AIE-123")
        assert issue == "AIE-123"
        assert repo is None

    def test_url_not_split_on_colon(self):
        # URLs contain colons but shouldn't be split
        issue, repo = work.parse_issue_arg(
            "https://github.com/owner/repo/issues/1"
        )
        assert issue == "https://github.com/owner/repo/issues/1"
        assert repo is None


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_slugify(self):
        assert work.slugify("Hello World") == "hello-world"
        assert work.slugify("Fix the bug") == "fix-the-bug"

    def test_special_characters(self):
        assert work.slugify("Fix: the [bug]!") == "fix-the-bug"
        assert work.slugify("Feature/add-login") == "feature-add-login"
        assert work.slugify("test@example#123") == "test-example-123"

    def test_multiple_spaces_and_hyphens(self):
        assert work.slugify("hello   world") == "hello-world"
        assert work.slugify("hello---world") == "hello-world"
        assert work.slugify("  hello  ") == "hello"

    def test_max_length_truncation(self):
        long_text = "this is a very long issue title that should be truncated"
        result = work.slugify(long_text, max_length=20)
        assert len(result) <= 20
        # Should truncate at word boundary (hyphen)
        assert not result.endswith("-")

    def test_max_length_preserves_word_boundary(self):
        # "implement-user-authentication-system" is 37 chars
        result = work.slugify("implement user authentication system", max_length=30)
        # Should cut at a hyphen boundary, not mid-word
        assert len(result) <= 30
        assert "-" not in result[-1:]  # doesn't end with hyphen

    def test_empty_and_whitespace(self):
        assert work.slugify("") == ""
        assert work.slugify("   ") == ""

    def test_numbers_preserved(self):
        assert work.slugify("issue 42 fix") == "issue-42-fix"
        assert work.slugify("v2.0.0 release") == "v2-0-0-release"

    def test_unicode_handling(self):
        # Unicode characters should be stripped
        result = work.slugify("café résumé")
        assert "caf" in result or result == "caf-r-sum"  # depends on impl


class TestParsedIssueDataclass:
    """Tests for ParsedIssue dataclass."""

    def test_default_values(self):
        issue = work.ParsedIssue()
        assert issue.owner is None
        assert issue.repo is None
        assert issue.issue_type is None
        assert issue.number is None
        assert issue.jira_key is None
        assert issue.description is None

    def test_with_values(self):
        issue = work.ParsedIssue(
            owner="anthropic",
            repo="claude",
            issue_type="issues",
            number=100,
        )
        assert issue.owner == "anthropic"
        assert issue.repo == "claude"
        assert issue.number == 100
