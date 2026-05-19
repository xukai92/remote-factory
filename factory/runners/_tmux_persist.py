"""Tmux persist — launch agents interactively in tmux with output capture."""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_SESSION_PREFIX = "factory-persist-"


def tmux_available() -> bool:
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def _ensure_session(session: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
    ).returncode == 0


async def run_in_tmux(
    prompt: str,
    task: str,
    cwd: Path,
    role: str,
    project_path: Path,
    *,
    timeout: float = 600.0,
    model: str | None = None,
    dangerously_skip_permissions: bool = True,
) -> tuple[str, int]:
    """Launch claude interactively in a tmux window and wait for completion.

    Output is captured via the `script` command. The factory blocks on
    `tmux wait-for` until the session exits, then reads the captured output.

    Returns (stdout, return_code).
    """
    run_id = uuid.uuid4().hex[:8]
    signal = f"factory-done-{run_id}"
    session = f"{_SESSION_PREFIX}{project_path.name}"
    window = f"{role}-{run_id}"

    tmpdir = Path(tempfile.mkdtemp(prefix="factory-tmux-"))
    logfile = tmpdir / "output.log"
    exitcode_file = tmpdir / "exitcode"
    wrapper_script = tmpdir / "wrapper.sh"

    cmd = ["claude", "--append-system-prompt", prompt]
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if model:
        cmd.extend(["--model", model])
    cmd.append(task)

    claude_cmd = shlex.join(cmd)
    wrapper_script.write_text(
        "#!/bin/bash\n"
        f"script -q -c {shlex.quote(claude_cmd)} {shlex.quote(str(logfile))}\n"
        f"echo $? > {shlex.quote(str(exitcode_file))}\n"
        f"tmux wait-for -S {shlex.quote(signal)}\n"
    )
    wrapper_script.chmod(0o755)

    has_session = _ensure_session(session)
    if has_session:
        result = subprocess.run(
            ["tmux", "new-window", "-t", session, "-n", window, str(wrapper_script)],
            cwd=cwd,
            capture_output=True,
        )
    else:
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "-n", window,
             "-x", "200", "-y", "50", str(wrapper_script)],
            cwd=cwd,
            capture_output=True,
        )

    if result.returncode != 0:
        logger.warning("Failed to create tmux window for %s: %s", role, result.stderr.decode()[:200])
        _cleanup(tmpdir)
        return f"Failed to create tmux window for {role}", 1

    logger.info("tmux_launched session=%s window=%s role=%s", session, window, role)

    try:
        wait_proc = await asyncio.create_subprocess_exec(
            "tmux", "wait-for", signal,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(wait_proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        wait_proc.kill()
        await wait_proc.wait()
        subprocess.run(
            ["tmux", "kill-window", "-t", f"{session}:{window}"],
            capture_output=True,
        )
        logger.error("tmux agent timed out after %ss: role=%s", timeout, role)
        _cleanup(tmpdir)
        return f"Agent timed out after {timeout}s", 1

    stdout = ""
    return_code = 1
    try:
        if logfile.exists():
            stdout = _strip_ansi(logfile.read_text(errors="replace"))
        if exitcode_file.exists():
            return_code = int(exitcode_file.read_text().strip())
    except (ValueError, OSError) as e:
        logger.warning("Failed to read tmux agent output: %s", e)
    finally:
        _cleanup(tmpdir)

    return stdout, return_code


def _cleanup(tmpdir: Path) -> None:
    try:
        for f in tmpdir.iterdir():
            f.unlink()
        tmpdir.rmdir()
    except OSError:
        pass
