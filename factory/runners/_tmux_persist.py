"""Alternative agent execution modes — tmux windows and background sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import subprocess
import sys
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


_DEFAULT_TMUX_TIMEOUT = 86400.0  # 24 hours — interactive sessions are user-driven


async def run_in_tmux(
    prompt: str,
    task: str,
    cwd: Path,
    role: str,
    project_path: Path,
    *,
    timeout: float = _DEFAULT_TMUX_TIMEOUT,
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
    print(f"Agent '{role}' launched in tmux session: {session}", file=sys.stderr)
    print(f"  tmux attach -t {session}    # attach and interact", file=sys.stderr)
    print("  /exit or Ctrl-d to finish   # factory resumes when you exit", file=sys.stderr)

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


def _parse_bg_session_id(output: str) -> str | None:
    """Parse session ID from `claude --bg` output.

    Expected format: 'backgrounded · <hex_id> [· <name>]'
    """
    for line in output.splitlines():
        if line.startswith("backgrounded"):
            parts = line.split("·")
            if len(parts) >= 2:
                return parts[1].strip()
    return None


_BG_POLL_INTERVAL = 5.0
_BG_TERMINAL_STATES = {"done", "completed", "failed", "stopped"}
_CLAUDE_JOBS_DIR = Path("~/.claude/jobs").expanduser()


def _read_session_state(session_id: str) -> dict | None:
    state_file = _CLAUDE_JOBS_DIR / session_id / "state.json"
    if not state_file.exists():
        return None
    try:
        import json
        return json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


async def run_in_background(
    prompt: str,
    task: str,
    cwd: Path,
    role: str,
    *,
    timeout: float = _DEFAULT_TMUX_TIMEOUT,
    model: str | None = None,
    dangerously_skip_permissions: bool = True,
) -> tuple[str, int]:
    """Launch claude as a background session via --bg (agent view).

    The session is visible in `claude agents`. The factory polls for
    completion and returns the output when the session finishes.

    Returns (stdout, return_code).
    """
    session_name = f"factory-{role}"

    cmd = ["claude", "--bg", "--name", session_name, "--append-system-prompt", prompt, task]
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    if model:
        cmd.extend(["--model", model])

    logger.info("Launching background agent: role=%s, cwd=%s", role, cwd)

    env = dict(os.environ)
    env["FACTORY_BG"] = "1"

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except FileNotFoundError:
        logger.error("'claude' CLI not found on PATH")
        return "Error: 'claude' CLI not found on PATH", 1
    except subprocess.TimeoutExpired:
        logger.error("claude --bg timed out during launch")
        return "Error: claude --bg timed out during launch", 1

    output = result.stdout + result.stderr
    session_id = _parse_bg_session_id(output)

    if result.returncode != 0 or not session_id:
        logger.warning("Failed to launch background agent: %s", output[:200])
        return f"Failed to launch background agent for {role}: {output[:200]}", 1

    print(f"Agent '{role}' launched in background: {session_id}", file=sys.stderr)
    print(f"  claude attach {session_id}    # attach to interact", file=sys.stderr)

    elapsed = 0.0
    while elapsed < timeout:
        await asyncio.sleep(_BG_POLL_INTERVAL)
        elapsed += _BG_POLL_INTERVAL

        state = _read_session_state(session_id)
        if state and state.get("state") in _BG_TERMINAL_STATES:
            session_output = ""
            if isinstance(state.get("output"), dict):
                session_output = state["output"].get("result", "")
            elif isinstance(state.get("output"), str):
                session_output = state["output"]

            is_success = state["state"] in ("done", "completed")
            return session_output, 0 if is_success else 1

    logger.error("Background agent timed out after %ss: role=%s", timeout, role)
    subprocess.run(["claude", "stop", session_id], capture_output=True)
    return f"Agent timed out after {timeout}s", 1
