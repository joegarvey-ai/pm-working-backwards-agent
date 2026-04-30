"""Tests for scripts/check_env.py MCP variable reporting.

Validates: Requirements 5.1, 6.1, 6.2, 6.3, 6.5

Runs the check_env script via subprocess with a controlled environment and
asserts the output for each of the three MIDWAY states (unset,
set-and-missing, set-and-present) and for SET vs NOT SET on each of the
four token and endpoint variables.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "check_env.py")


def _run_check_env(env_overrides: dict[str, str | None], cwd: Path) -> str:
    """Run check_env.py with a controlled environment and return stdout.

    *cwd* should be a temp directory so that ``load_dotenv()`` inside the
    script does not pick up the project's ``.env`` file.
    """
    clean_env: dict[str, str] = {}
    for keep in ("PATH", "VIRTUAL_ENV", "HOME", "SYSTEMROOT", "COMSPEC"):
        if keep in os.environ:
            clean_env[keep] = os.environ[keep]

    for k, v in env_overrides.items():
        if v is not None:
            clean_env[k] = v

    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        env=clean_env,
        cwd=str(cwd),
        timeout=15,
    )
    return result.stdout


# ── MIDWAY_COOKIE_PATH: three states ────────────────────────────────


class TestMidwayCookiePath:
    """MIDWAY_COOKIE_PATH reports NOT SET, SET, or MISCONFIGURED."""

    def test_unset(self, tmp_path: Path):
        out = _run_check_env({}, cwd=tmp_path)
        assert "MIDWAY_COOKIE_PATH: NOT SET" in out

    def test_set_and_present(self, tmp_path: Path):
        cookie = tmp_path / "midway_cookie"
        cookie.write_text("cookie-content")
        out = _run_check_env({"MIDWAY_COOKIE_PATH": str(cookie)}, cwd=tmp_path)
        assert "MIDWAY_COOKIE_PATH: SET" in out
        assert "MISCONFIGURED" not in out

    def test_set_but_missing(self, tmp_path: Path):
        missing = tmp_path / "no_such_cookie"
        out = _run_check_env({"MIDWAY_COOKIE_PATH": str(missing)}, cwd=tmp_path)
        assert "MIDWAY_COOKIE_PATH: MISCONFIGURED" in out
        assert "file missing" in out


# ── Token and endpoint variables: SET vs NOT SET ─────────────────────


MCP_VARS = [
    "BUILDER_MCP_TOKEN",
    "BUILDER_MCP_ENDPOINT",
    "OUTLOOK_MCP_TOKEN",
    "OUTLOOK_MCP_ENDPOINT",
]


class TestMcpTokenAndEndpointVars:
    """Each MCP variable reports SET or NOT SET."""

    @pytest.mark.parametrize("var", MCP_VARS)
    def test_set(self, var: str, tmp_path: Path):
        out = _run_check_env({var: "some-value"}, cwd=tmp_path)
        assert f"{var}: SET" in out

    @pytest.mark.parametrize("var", MCP_VARS)
    def test_unset(self, var: str, tmp_path: Path):
        out = _run_check_env({}, cwd=tmp_path)
        assert f"{var}: NOT SET" in out


# ── Secret values are never printed ──────────────────────────────────


class TestNoSecretLeakage:
    """The script must not print actual secret values."""

    def test_token_value_not_in_output(self, tmp_path: Path):
        secret = "super-secret-token-12345"
        out = _run_check_env({"BUILDER_MCP_TOKEN": secret}, cwd=tmp_path)
        assert secret not in out
        assert f"BUILDER_MCP_TOKEN: SET (len={len(secret)})" in out

    def test_cookie_path_value_uses_len(self, tmp_path: Path):
        cookie = tmp_path / "midway_cookie"
        cookie.write_text("cookie-content")
        path_str = str(cookie)
        out = _run_check_env({"MIDWAY_COOKIE_PATH": path_str}, cwd=tmp_path)
        assert f"len={len(path_str)}" in out
