"""Tests for the tmux persist helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from factory.runners._tmux_persist import (
    _SESSION_PREFIX,
    open_resume_window,
    tmux_available,
)


class TestTmuxAvailable:
    def test_returns_true_when_tmux_found(self) -> None:
        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert tmux_available() is True
            mock_run.assert_called_once_with(["tmux", "-V"], capture_output=True, check=True)

    def test_returns_false_when_tmux_not_found(self) -> None:
        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            assert tmux_available() is False

    def test_returns_false_when_tmux_fails(self) -> None:
        import subprocess

        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "tmux")
            assert tmux_available() is False


class TestOpenResumeWindow:
    def test_creates_new_session_when_none_exists(self, tmp_path: Path) -> None:
        session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        cwd = project_path
        role = "builder"

        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            # has-session returns 1 (no session)
            has_session_result = MagicMock(returncode=1)
            new_session_result = MagicMock(returncode=0)
            mock_run.side_effect = [has_session_result, new_session_result]

            result = open_resume_window(session_id, project_path, role, cwd)

            assert result is True
            expected_session = f"{_SESSION_PREFIX}{project_path.name}"
            expected_window = f"{role}-{session_id[:8]}"
            resume_cmd = f"claude --resume {session_id}"

            assert mock_run.call_count == 2
            mock_run.assert_any_call(
                ["tmux", "has-session", "-t", expected_session],
                capture_output=True,
            )
            mock_run.assert_any_call(
                ["tmux", "new-session", "-d", "-s", expected_session, "-n", expected_window,
                 "-x", "200", "-y", "50", resume_cmd],
                cwd=cwd,
            )

    def test_creates_new_window_when_session_exists(self, tmp_path: Path) -> None:
        session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        cwd = project_path
        role = "researcher"

        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            # has-session returns 0 (session exists)
            has_session_result = MagicMock(returncode=0)
            new_window_result = MagicMock(returncode=0)
            mock_run.side_effect = [has_session_result, new_window_result]

            result = open_resume_window(session_id, project_path, role, cwd)

            assert result is True
            expected_session = f"{_SESSION_PREFIX}{project_path.name}"
            expected_window = f"{role}-{session_id[:8]}"
            resume_cmd = f"claude --resume {session_id}"

            assert mock_run.call_count == 2
            mock_run.assert_any_call(
                ["tmux", "has-session", "-t", expected_session],
                capture_output=True,
            )
            mock_run.assert_any_call(
                ["tmux", "new-window", "-t", expected_session, "-n", expected_window, resume_cmd],
                cwd=cwd,
            )

    def test_returns_false_on_failure(self, tmp_path: Path) -> None:
        session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        project_path = tmp_path / "my-project"
        project_path.mkdir()

        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            has_session_result = MagicMock(returncode=1)
            new_session_result = MagicMock(returncode=1)
            mock_run.side_effect = [has_session_result, new_session_result]

            result = open_resume_window(session_id, project_path, "builder", project_path)

            assert result is False

    def test_window_name_uses_session_id_prefix(self, tmp_path: Path) -> None:
        session_id = "12345678-abcd-efgh-ijkl-mnopqrstuvwx"
        project_path = tmp_path / "test-proj"
        project_path.mkdir()

        with patch("factory.runners._tmux_persist.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            open_resume_window(session_id, project_path, "ceo", project_path)

            new_window_call = mock_run.call_args_list[1]
            cmd_args = new_window_call[0][0]
            # Window name should be role-first8chars
            assert "ceo-12345678" in cmd_args
