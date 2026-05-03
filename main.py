# main.py — Neural Terminal entry point

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import asyncio
import glob
import json
import signal
import subprocess
import socket
import time
from datetime import datetime
from typing import List, Tuple

from ui import neural_ui as ui, input_handler, console
from ui.colors import C


# ───────────────── SESSION FILE TRACKING ───────────────── #

_session_existing_files: set = set()
_session_created_files:  List[Tuple[str, int]] = []   # (rel_path, line_count)
_session_modified_files: List[str] = []


def _snapshot_cwd():
    """Record all files that exist BEFORE the session starts."""
    global _session_existing_files
    cwd = os.getcwd()
    skip_dirs = {".venv", ".git", "__pycache__", ".backups", "node_modules"}
    existing = set()
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for f in files:
            existing.add(os.path.relpath(os.path.join(root, f), cwd))
    _session_existing_files = existing


def _scan_new_files():
    """Find files created this session that weren't there at startup."""
    global _session_created_files
    cwd      = os.getcwd()
    skip_dirs = {".venv", ".git", "__pycache__", ".backups", "node_modules"}
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
                 ".go", ".rs", ".java", ".rb", ".php", ".sh", ".cpp", ".c"}
    found = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), cwd)
            if rel not in _session_existing_files:
                ext = os.path.splitext(f)[1].lower()
                if ext in code_exts:
                    try:
                        with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                            lines = fh.read().count("\n") + 1
                    except Exception:
                        lines = 0
                    found.append((rel, lines))
    _session_created_files = found
    return found


def _ensure_saves_dirs():
    for sub in ("charts", "docs", "sessions", "scripts"):
        os.makedirs(os.path.join(os.getcwd(), "saves", sub), exist_ok=True)


# ───────────────── MCP SERVER ───────────────── #

_mcp_process = None


def _is_mcp_running(host="localhost", port=8000) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=1)
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def _find_mcp_server_script():
    candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    return candidate if os.path.isfile(candidate) else None


def _start_mcp_server() -> bool:
    global _mcp_process
    script = _find_mcp_server_script()
    if script is None:
        return False
    _mcp_process = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.getcwd(),
    )
    for _ in range(30):
        time.sleep(0.5)
        if _is_mcp_running():
            return True
        if _mcp_process.poll() is not None:
            return False
    return False


def _ensure_mcp_server() -> bool:
    if _is_mcp_running():
        return True
    return _start_mcp_server()


def _cleanup_mcp_server():
    global _mcp_process
    if _mcp_process and _mcp_process.poll() is None:
        _mcp_process.terminate()
        try:
            _mcp_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _mcp_process.kill()


# ───────────────── INTERRUPT HANDLING ───────────────── #

_current_task: asyncio.Task = None


async def _run_agent(agent, user_input: str):
    global _current_task
    _current_task = asyncio.current_task()
    try:
        await agent.chat(user_input)
    except asyncio.CancelledError:
        ui.cancel_current()
    except Exception as e:
        ui.print_error(str(e))
    finally:
        ui.stop_thinking()
        _current_task = None


# ───────────────── SESSION END ───────────────── #

def _end_session(agent, model: str, backend: str):
    _ensure_saves_dirs()

    # Scan for new code files
    new_files = _scan_new_files()
    if new_files:
        to_delete = ui.show_files_created_dialog(new_files)
        for path in to_delete:
            if path not in _session_existing_files:
                abs_path = os.path.join(os.getcwd(), path)
                try:
                    ans = console.input(
                        f"  [bold {C['amber']}]⚠  Delete {path}? "
                        f"This cannot be undone. [y/N] ❯ [/]"
                    ).strip().lower()
                    if ans == "y":
                        os.remove(abs_path)
                        ui.print_info(f"🗑  Deleted: {path}")
                except Exception:
                    pass

    # Save session log
    try:
        from ui.formatters import save_session_log
        stats       = agent.get_token_stats()
        created_rel = [p for p, _ in _session_created_files]
        log_path    = save_session_log(
            cwd=os.getcwd(),
            model=model,
            backend=backend,
            session_start=ui._session_start,
            steps=ui._steps,
            messages=agent.messages,
            files_created=created_rel,
            files_modified=_session_modified_files,
            total_tokens=stats["total_tokens"],
            total_calls=stats["steps"],
        )
        if log_path:
            ui.print_info(f"💾  Session saved → {log_path}")
    except Exception:
        pass


# ───────────────── SHORTCUTS BAR ───────────────── #

def _print_shortcuts():
    console.print(
        f"  [dim {C['gray']}]"
        "/help · /clear · /compact · /tokens · /model · /mcp · "
        "/expand · /history · /exit"
        "[/]"
    )
    console.print(f"  [dim {C['gray']}]{'─' * 64}[/]")
    console.print()


# ───────────────── MAIN ───────────────── #

def main():
    asyncio.run(_main())


async def _main():
    from core.agent import Agent
    from llm_model import get_active_backend, NVIDIA_MODEL

    _snapshot_cwd()
    _ensure_saves_dirs()

    backend       = get_active_backend()
    model_display = NVIDIA_MODEL.split("/")[-1] if "/" in NVIDIA_MODEL else NVIDIA_MODEL
    cwd           = os.path.basename(os.getcwd()) + "/"

    ui.startup_sequence(_ensure_mcp_server, backend=backend)
    ui.init_status_bar(model_display, backend, cwd)
    _print_shortcuts()

    agent = Agent()

    # Ctrl+C cancels current task instead of exiting
    loop = asyncio.get_event_loop()

    def _sigint_handler(signum, frame):
        global _current_task
        if _current_task and not _current_task.done():
            loop.call_soon_threadsafe(_current_task.cancel)
        else:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, input_handler.prompt
                )
            except (EOFError, KeyboardInterrupt):
                break

            if user_input is None:
                break
            if not user_input:
                continue

            if user_input.startswith("/"):
                cmd = user_input.lower().split()[0]

                if cmd in ("/quit", "/exit", "/q"):
                    break
                elif cmd == "/help":
                    from ui.components import print_help
                    print_help(console)
                elif cmd == "/expand":
                    ui.do_expand()
                elif cmd == "/history":
                    ui.do_history()
                elif cmd == "/tokens":
                    from ui.components import print_token_stats
                    print_token_stats(console, agent.get_token_stats(), ui._session_start)
                elif cmd == "/compact":
                    ui.do_compact(agent)
                elif cmd == "/clear":
                    ui.do_clear(agent)
                    _print_shortcuts()
                elif cmd == "/model":
                    await ui.do_model_submenu(input_handler, agent)
                    from llm_model import get_active_backend, NVIDIA_MODEL as NVM
                    model_display = NVM.split("/")[-1] if "/" in NVM else NVM
                    backend       = get_active_backend()
                elif cmd == "/mcp":
                    await ui.do_mcp_submenu(input_handler)
                else:
                    ui.print_warning(f"Unknown command: {cmd}")
                continue

            ui.print_user_message(user_input)
            await _run_agent(agent, user_input)

    finally:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        _cleanup_mcp_server()
        from llm_model import get_active_backend, NVIDIA_MODEL as NVM_FINAL
        _end_session(agent, NVM_FINAL.split("/")[-1] if "/" in NVM_FINAL else NVM_FINAL,
                     get_active_backend())
        ui.print_goodbye()


if __name__ == "__main__":
    main()
