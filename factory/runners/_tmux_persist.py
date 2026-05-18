"""Tmux persist helper — open a resume window after headless agent run."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_SESSION_PREFIX = "factory-persist-"


def tmux_available() -> bool:
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def open_resume_window(
    session_id: str,
    project_path: Path,
    role: str,
    cwd: Path,
) -> bool:
    """Create a tmux window running `claude --resume <session_id>`.

    Uses session `factory-persist-<project_name>`, creating it if needed.
    Returns True if the window was created, False on failure.
    """
    session = f"{_SESSION_PREFIX}{project_path.name}"
    window = f"{role}-{session_id[:8]}"
    resume_cmd = f"claude --resume {session_id}"

    has_session = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
    ).returncode == 0

    if has_session:
        result = subprocess.run(
            ["tmux", "new-window", "-t", session, "-n", window, resume_cmd],
            cwd=cwd,
        )
    else:
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-n", window,
             "-x", "200", "-y", "50", resume_cmd],
            cwd=cwd,
        )

    if result.returncode != 0:
        logger.warning("Failed to create tmux resume window for %s", role)
        return False

    logger.info(
        "tmux_persist_opened session=%s window=%s session_id=%s",
        session, window, session_id,
    )
    return True
