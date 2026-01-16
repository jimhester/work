"""Tests for shell hook scripts using shellcheck."""

import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
SHELL_SCRIPTS = list(HOOKS_DIR.glob("*.sh"))


@pytest.fixture(scope="module")
def shellcheck_available():
    """Check if shellcheck is available, skip tests if not."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed")


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shellcheck(shellcheck_available, script):
    """Run shellcheck on each shell script."""
    result = subprocess.run(
        ["shellcheck", "-x", str(script)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"shellcheck errors in {script.name}:\n{result.stdout}{result.stderr}")


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_script_has_shebang(script):
    """Verify each script has a proper shebang."""
    content = script.read_text()
    first_line = content.split("\n")[0]
    assert first_line.startswith("#!/"), f"{script.name} missing shebang"
    assert "bash" in first_line or "sh" in first_line, f"{script.name} shebang not bash/sh"


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_script_is_executable(script):
    """Verify each script has executable permissions."""
    assert script.stat().st_mode & 0o111, f"{script.name} is not executable"
