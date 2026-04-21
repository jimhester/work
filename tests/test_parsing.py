"""Tests for issue parsing and text processing functions."""

import subprocess
from pathlib import Path

import click
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


class TestParseRemoteUrl:
    """Tests for parse_remote_url function."""

    def test_https_url_with_git_suffix(self):
        assert work.parse_remote_url(
            "https://github.com/owner/repo.git"
        ) == ("github.com", "owner", "repo")

    def test_https_url_without_git_suffix(self):
        assert work.parse_remote_url(
            "https://github.com/owner/repo"
        ) == ("github.com", "owner", "repo")

    def test_ssh_url(self):
        assert work.parse_remote_url(
            "git@github.com:owner/repo.git"
        ) == ("github.com", "owner", "repo")

    def test_netflix_ghe_https(self):
        assert work.parse_remote_url(
            "https://github.netflix.net/corp/project.git"
        ) == ("github.netflix.net", "corp", "project")

    def test_netflix_ghe_ssh(self):
        assert work.parse_remote_url(
            "git@github.netflix.net:corp/project.git"
        ) == ("github.netflix.net", "corp", "project")

    def test_http_url(self):
        assert work.parse_remote_url(
            "http://github.com/owner/repo.git"
        ) == ("github.com", "owner", "repo")

    def test_complex_repo_names(self):
        assert work.parse_remote_url(
            "https://github.com/my-org/my-cool-repo.git"
        ) == ("github.com", "my-org", "my-cool-repo")

    def test_repo_name_with_dots(self):
        # GitHub allows dots in repo names
        assert work.parse_remote_url(
            "https://github.com/owner/foo.bar.git"
        ) == ("github.com", "owner", "foo.bar")
        assert work.parse_remote_url(
            "git@github.com:owner/foo.bar.baz.git"
        ) == ("github.com", "owner", "foo.bar.baz")

    def test_non_github_host_returns_none(self):
        assert work.parse_remote_url("https://gitlab.com/owner/repo.git") is None
        assert work.parse_remote_url("https://bitbucket.org/owner/repo.git") is None

    def test_invalid_url_returns_none(self):
        assert work.parse_remote_url("not a url") is None
        assert work.parse_remote_url("") is None

    def test_trailing_whitespace_tolerated(self):
        # Git remote output often has trailing whitespace/newline
        assert work.parse_remote_url(
            "https://github.com/owner/repo.git\n"
        ) == ("github.com", "owner", "repo")


def _init_git_repo_with_remotes(tmp_path: Path, remotes: dict[str, str]) -> Path:
    """Create a tmp git repo with the given remotes. Returns the repo path.

    Writes the remotes directly into .git/config to sidestep any global
    git ``insteadOf`` URL rewrites on the host machine.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    config_path = repo / ".git" / "config"
    with open(config_path, "a") as f:
        for name, url in remotes.items():
            f.write(
                f'[remote "{name}"]\n'
                f'\turl = {url}\n'
                f'\tfetch = +refs/heads/*:refs/remotes/{name}/*\n'
            )
    return repo


class TestGetGitRemotes:
    """Tests for get_git_remotes function."""

    def test_no_remotes(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(tmp_path, {})
        monkeypatch.chdir(repo)
        assert work.get_git_remotes() == []

    def test_single_remote(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/owner/repo.git"},
        )
        monkeypatch.chdir(repo)
        remotes = work.get_git_remotes()
        assert remotes == [("origin", "github.com", "owner", "repo")]

    def test_multiple_remotes_same_host(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.com/user/repo.git",
                "upstream": "https://github.com/other/repo.git",
            },
        )
        monkeypatch.chdir(repo)
        remotes = work.get_git_remotes()
        assert len(remotes) == 2
        names = {r[0] for r in remotes}
        assert names == {"origin", "upstream"}

    def test_multiple_remotes_different_hosts(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.netflix.net/corp/proj.git",
                "upstream": "https://github.com/posit-dev/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        remotes = work.get_git_remotes()
        assert len(remotes) == 2
        remotes_by_name = {r[0]: r for r in remotes}
        assert remotes_by_name["origin"] == (
            "origin", "github.netflix.net", "corp", "proj"
        )
        assert remotes_by_name["upstream"] == (
            "upstream", "github.com", "posit-dev", "proj"
        )

    def test_ignores_non_github_remotes(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.com/owner/repo.git",
                "other": "https://gitlab.com/owner/repo.git",
            },
        )
        monkeypatch.chdir(repo)
        remotes = work.get_git_remotes()
        assert len(remotes) == 1
        assert remotes[0][0] == "origin"

    def test_dedupes_fetch_and_push(self, tmp_path, monkeypatch):
        # `git remote -v` outputs each remote twice (fetch and push)
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/owner/repo.git"},
        )
        monkeypatch.chdir(repo)
        remotes = work.get_git_remotes()
        # Should dedupe to a single entry
        assert len(remotes) == 1


class TestResolveTargetRepo:
    """Tests for resolve_target_repo function."""

    def test_single_remote_no_explicit(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/owner/repo.git"},
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        result = work.resolve_target_repo()
        assert result == ("github.com", "owner", "repo")

    def test_single_ghe_remote(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.netflix.net/corp/proj.git"},
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        result = work.resolve_target_repo()
        assert result == ("github.netflix.net", "corp", "proj")

    def test_multiple_remotes_same_host_prefers_origin(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "upstream": "https://github.com/upstream/proj.git",
                "origin": "https://github.com/forker/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        result = work.resolve_target_repo()
        assert result == ("github.com", "forker", "proj")

    def test_multiple_hosts_errors_without_gh_host(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.netflix.net/corp/proj.git",
                "upstream": "https://github.com/posit-dev/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        with pytest.raises(click.ClickException) as excinfo:
            work.resolve_target_repo()
        assert "multiple" in str(excinfo.value.message).lower()
        assert "github.netflix.net" in excinfo.value.message
        assert "github.com" in excinfo.value.message

    def test_multiple_hosts_with_gh_host_picks_match(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.netflix.net/corp/proj.git",
                "upstream": "https://github.com/posit-dev/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        result = work.resolve_target_repo(gh_host="github.netflix.net")
        assert result == ("github.netflix.net", "corp", "proj")

    def test_gh_host_with_no_matching_remote_errors(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/owner/repo.git"},
        )
        monkeypatch.chdir(repo)
        with pytest.raises(click.ClickException) as excinfo:
            work.resolve_target_repo(gh_host="github.netflix.net")
        assert "github.netflix.net" in excinfo.value.message

    def test_explicit_repo_overrides_remote_detection(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.netflix.net/corp/proj.git",
                "upstream": "https://github.com/posit-dev/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        # Explicit repo override avoids the ambiguity
        result = work.resolve_target_repo(explicit_repo="posit-dev/proj")
        assert result == (None, "posit-dev", "proj")

    def test_explicit_repo_with_host_prefix(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/owner/repo.git"},
        )
        monkeypatch.chdir(repo)
        result = work.resolve_target_repo(
            explicit_repo="github.netflix.net/corp/proj"
        )
        assert result == ("github.netflix.net", "corp", "proj")

    def test_no_remotes_returns_none_without_explicit(self, tmp_path, monkeypatch):
        repo = _init_git_repo_with_remotes(tmp_path, {})
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        assert work.resolve_target_repo() is None


class TestParseIssueArgRepoScoped:
    """Tests for parse_issue_arg with owner/repo:N syntax."""

    def test_owner_repo_prefix(self):
        issue, repo = work.parse_issue_arg("owner/repo:42")
        assert issue == "42"
        assert repo == "owner/repo"

    def test_host_owner_repo_prefix(self):
        issue, repo = work.parse_issue_arg("github.netflix.net/corp/proj:42")
        assert issue == "42"
        assert repo == "github.netflix.net/corp/proj"


class TestSpawnInvocation:
    """Tests for shell command building used by spawn_in_new_tab."""

    def test_bare_issue_no_repo_flag(self, tmp_path):
        cmd = work._build_work_invocation("42", tmp_path / "work")
        assert "--here" in cmd
        assert "42" in cmd
        assert "--repo" not in cmd

    def test_bare_issue_with_repo_override(self, tmp_path):
        cmd = work._build_work_invocation(
            "42", tmp_path / "work", repo_override="owner/name"
        )
        assert "--repo owner/name" in cmd
        assert "--here 42" in cmd

    def test_issue_with_shell_metachars_quoted(self, tmp_path):
        # Inputs with shell metacharacters must be quoted; otherwise the
        # child shell would interpret them.
        cmd = work._build_work_invocation(
            "feature; rm -rf /",
            tmp_path / "work",
        )
        # shlex.quote wraps dangerous input in single quotes
        assert "'feature; rm -rf /'" in cmd

    def test_env_prefix_with_gh_host(self, monkeypatch):
        monkeypatch.setenv("GH_HOST", "github.netflix.net")
        prefix = work._build_spawn_env_prefix()
        assert "GH_HOST=github.netflix.net" in prefix

    def test_env_prefix_without_gh_host(self, monkeypatch):
        monkeypatch.delenv("GH_HOST", raising=False)
        prefix = work._build_spawn_env_prefix()
        assert prefix == ""


class TestValidateIssuesBeforeSpawn:
    """Tests for the upfront issue validation that prevents spawning
    workers against the wrong repo.
    """

    def test_ambiguous_remotes_without_disambiguator(
        self, tmp_path, monkeypatch
    ):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.netflix.net/corp/proj.git",
                "upstream": "https://github.com/posit-dev/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        with pytest.raises(click.ClickException) as excinfo:
            work.validate_issues_before_spawn(("42",))
        # Message should mention ambiguity and show both hosts
        assert "github.netflix.net" in excinfo.value.message
        assert "github.com" in excinfo.value.message

    def test_explicit_repo_override_resolves_cleanly(
        self, tmp_path, monkeypatch, mocker
    ):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {
                "origin": "https://github.netflix.net/corp/proj.git",
                "upstream": "https://github.com/posit-dev/proj.git",
            },
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        # Mock fetch_issue_title to simulate a successful lookup
        mocker.patch.object(
            work, "fetch_issue_title", return_value="Mock issue title"
        )
        # Should not raise when an explicit repo disambiguates
        work.validate_issues_before_spawn(
            ("42",), repo_override="github.netflix.net/corp/proj"
        )

    def test_missing_issue_surfaces_in_error(
        self, tmp_path, monkeypatch, mocker
    ):
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/owner/repo.git"},
        )
        monkeypatch.chdir(repo)
        monkeypatch.delenv("GH_HOST", raising=False)
        # Title lookup returns None (issue doesn't exist)
        mocker.patch.object(work, "fetch_issue_title", return_value=None)
        with pytest.raises(click.ClickException) as excinfo:
            work.validate_issues_before_spawn(("42",))
        assert "42" in excinfo.value.message
        assert "github.com/owner/repo" in excinfo.value.message

    def test_jira_keys_are_skipped(self, tmp_path, monkeypatch, mocker):
        # JIRA keys shouldn't be validated against GitHub
        repo = _init_git_repo_with_remotes(tmp_path, {})
        monkeypatch.chdir(repo)
        mock_fetch = mocker.patch.object(
            work, "fetch_issue_title", return_value="title"
        )
        work.validate_issues_before_spawn(("AIE-123",))
        mock_fetch.assert_not_called()

    def test_url_validated_against_url_host(
        self, tmp_path, monkeypatch, mocker
    ):
        # A full URL should be validated against its URL's host, not the
        # repo's git remotes
        repo = _init_git_repo_with_remotes(
            tmp_path,
            {"origin": "https://github.com/different/repo.git"},
        )
        monkeypatch.chdir(repo)
        mock_fetch = mocker.patch.object(
            work, "fetch_issue_title", return_value="title"
        )
        work.validate_issues_before_spawn(
            ("https://github.netflix.net/corp/proj/issues/5",)
        )
        # fetch_issue_title should be called with host-prefixed repo
        call_kwargs = mock_fetch.call_args
        assert call_kwargs.kwargs.get("repo") == "github.netflix.net/corp/proj"

    def test_repo_flag_with_non_numeric_errors(self, tmp_path, monkeypatch):
        # `work --repo owner/name "some text"` is a user error — the repo
        # flag only makes sense with a numeric issue. The validator must
        # surface this BEFORE spawning so it fails in the same place as
        # the child `work --here` would.
        repo = _init_git_repo_with_remotes(
            tmp_path, {"origin": "https://github.com/owner/repo.git"}
        )
        monkeypatch.chdir(repo)
        with pytest.raises(click.ClickException) as excinfo:
            work.validate_issues_before_spawn(
                ("not-a-number",), repo_override="owner/name"
            )
        assert "numeric issue number" in excinfo.value.message

    def test_plain_description_skipped(self, tmp_path, monkeypatch, mocker):
        # Without --repo/prefix, non-numeric input is a feature
        # description and should be passed through without validation.
        repo = _init_git_repo_with_remotes(
            tmp_path, {"origin": "https://github.com/owner/repo.git"}
        )
        monkeypatch.chdir(repo)
        mock_fetch = mocker.patch.object(
            work, "fetch_issue_title", return_value="title"
        )
        work.validate_issues_before_spawn(("add dark mode",))
        mock_fetch.assert_not_called()
