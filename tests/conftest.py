"""
Pytest configuration and fixtures for testing the work CLI.

This module handles importing the `work` script as a module despite it being
a standalone uv script without a .py extension.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Iterator

import pytest


# =============================================================================
# Import the work script as a module
# =============================================================================

def _load_work_module():
    """Load the work script as a Python module."""
    work_script = Path(__file__).parent.parent / "work"
    spec = importlib.util.spec_from_loader(
        "work",
        loader=None,
        origin=str(work_script),
    )
    assert spec is not None, "Failed to create module spec for work script"
    module = importlib.util.module_from_spec(spec)

    # IMPORTANT: Register in sys.modules BEFORE exec so dataclass decorator works
    sys.modules["work"] = module
    module.__name__ = "work"

    # Read and exec the script content
    with open(work_script) as f:
        source = f.read()

    # Compile and execute in module namespace
    code = compile(source, work_script, "exec")
    exec(code, module.__dict__)

    return module


# Load once at import time
work = _load_work_module()


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch) -> Iterator[Path]:
    """
    Create a temporary database for testing.

    Patches the global config to use the temp directory.
    """
    db_dir = tmp_path / ".worktrees"
    db_dir.mkdir()
    db_path = db_dir / "work-sessions.db"

    # Patch the config object's worktree_base
    monkeypatch.setattr(work.config, "worktree_base", db_dir)

    yield db_path


@pytest.fixture
def initialized_db(temp_db: Path) -> Path:
    """Provide an initialized database with schema."""
    work.init_db()
    return temp_db


@pytest.fixture
def sample_worker(initialized_db: Path) -> int:
    """Create a sample worker and return its ID."""
    return work.db_register_worker(
        repo_path="/home/user/repos/myrepo",
        repo_name="myrepo",
        issue_number=42,
        branch="issue-42-fix-bug",
        worktree_path="/home/user/.worktrees/myrepo/issue-42-fix-bug",
        pid=12345,
    )


@pytest.fixture
def temp_work_config(tmp_path: Path) -> Path:
    """Create a temporary .work.toml file."""
    config_path = tmp_path / ".work.toml"
    config_path.write_text('''
worker_guidelines = "Always write tests"
review_guidelines = "Check for security issues"
review_strictness = "strict"
require_pre_merge_review = true
''')
    return config_path
