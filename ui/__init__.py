# ui/__init__.py — NeuralUI facade

import os
import time
import threading
from datetime import datetime
from typing import Any, Callable, List, Optional

from rich.console import Console
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner

from ui.colors import C, THEME
from ui.animations import run_startup_sequence
from ui.components import (
    StatusBar, ThinkingIndicator, ThoughtBlock,
    print_user_message, print_action, print_observation,
    print_answer, print_error, print_warning, print_info,
    print_success_line, print_cancelled, print_stopped,
    print_loop_error, print_step_indicator,
    print_tokens, print_first_token, print_permission_prompt,
    print_help, print_token_stats, print_mcp_servers,
    print_full_result, print_history, animated_clear,
    print_files_created,
)
from ui.input_handler import InputHandler

console = Console(theme=THEME, highlight=False)


class NeuralUI:
    def __init__(self):
        self._console         = console
        self._status_bar:     Optional[StatusBar]    = None
        self._thinking:       ThinkingIndicator      = ThinkingIndicator(console)
        self._thought_block:  ThoughtBlock           = ThoughtBlock(console)
        self._session_start:  datetime               = datetime.now()
        self._lock            = threading.Lock()
        self._total_tokens    = 0
        self._total_calls     = 0
        self._current_step    = 0
        self._step_start      = time.time()

        # /expand storage
        self._last_result:    str  = ""
        self._last_tool:      str  = ""

        # /history storage
        self._steps:          List[dict] = []

        # ESC ESC cancel ref
        self._cancel_flag:    threading.Event = threading.Event()

        # model/backend tracking
        self._model   = ""
        self._backend = ""
        self._cwd     = os.path.basename(os.getcwd()) + "/"

    # ── Startup ── #

    def startup_sequence(self, mcp_init_fn: Callable[[], bool], backend: str = ""):
        result = run_startup_sequence(self._console, mcp_init_fn, backend=backend)
        return result

    def init_status_bar(self, model: str, backend: str, cwd: str):
        self._model   = model
        self._backend = backend
        self._cwd     = cwd
        self._status_bar = StatusBar(self._console, model, backend, cwd)
        self._status_bar.print()

    def refresh_status_bar(self):
        if self._status_bar:
            self._status_bar.print()

    # ── User message ── #

    def print_user_message(self, text: str):
        self._step_start   = time.time()
        self._current_step = 0
        print_user_message(self._console, text)

    # ── Thinking indicator ── #

    def start_thinking(self, text: str = "thinking"):
        self._thinking.start(text)

    def update_thinking(self, text: str):
        self._thinking.update(text)

    def stop_thinking(self):
        self._thinking.stop()

    # ── Thought streaming ── #

    def begin_thought(self, step: int = 0):
        self._thinking.stop()
        self._thought_block.begin(step)

    def stream_thought(self, token: str):
        self._thought_block.stream_token(token)

    def end_thought(self):
        text = self._thought_block.get_text()
        self._thought_block.end()
        if text.strip():
            self._steps.append({
                "step":    self._current_step,
                "type":    "thought",
                "summary": text.strip()[:80],
            })

    # ── Action ── #

    def print_action(self, tool_name: str, args: dict, step: int = 0):
        self._thinking.stop()
        self._current_step = step
        print_action(self._console, tool_name, args, step)

        key_val = next(
            (str(v)[:50] for k, v in args.items()
             if k in ("path", "command", "query", "pattern", "url")),
            ""
        )
        self._steps.append({
            "step":    step,
            "type":    "action",
            "summary": f"{tool_name}({key_val!r})" if key_val else tool_name,
        })

    # ── Observation ── #

    def print_observation(self, result: Any, step: int = 0, tool_name: str = ""):
        result_str = result if isinstance(result, str) else str(result)
        # Store for /expand
        if len(result_str) > 50:
            self._last_result = result_str
            self._last_tool   = tool_name
        print_observation(self._console, result_str, tool_name=tool_name, step=step)
        lines = len(result_str.splitlines())
        self._steps.append({
            "step":    step,
            "type":    "observe",
            "summary": f"{lines} lines returned" if lines > 1 else result_str[:60],
        })

    # ── Answer ── #

    def print_answer(self, text: str, tool_calls: int = 0,
                     tokens: int = 0, elapsed: float = 0.0):
        self._thinking.stop()
        print_answer(self._console, text, tool_calls, tokens, elapsed)
        self._steps.append({
            "step":    self._current_step,
            "type":    "answer",
            "summary": text.strip()[:80],
        })

    # ── Status bar ── #

    def update_status(self, tokens: int = 0, calls: int = 0):
        self._total_tokens += tokens
        self._total_calls  += calls
        if self._status_bar:
            self._status_bar.update(tokens, calls)

    # ── Step indicator ── #

    def print_step_indicator(self, step: int, max_steps: int):
        print_step_indicator(self._console, step, max_steps)

    # ── Token line ── #

    def print_tokens(self, inp: int, out: int, elapsed: float, model: str = ""):
        print_tokens(self._console, inp, out, elapsed, model)

    def print_first_token(self, elapsed: float):
        print_first_token(self._console, elapsed)

    # ── Errors / warnings ── #

    def print_error(self, message: str):
        self._thinking.stop()
        print_error(self._console, message)

    def print_warning(self, message: str):
        print_warning(self._console, message)

    def print_info(self, message: str):
        print_info(self._console, message)

    def print_success(self, message: str):
        print_success_line(self._console, message)

    def print_loop_error(self, message: str):
        self._thinking.stop()
        print_loop_error(self._console, message)

    def cancel_current(self):
        self._thinking.stop()
        self._thought_block.end()
        print_cancelled(self._console)

    def stop_current(self):
        self._thinking.stop()
        self._thought_block.end()
        print_stopped(self._console, self._total_tokens)

    # ── Permission prompt ── #

    def print_permission_prompt(self, tool_name: str, params: dict) -> bool:
        return print_permission_prompt(self._console, tool_name, params)

    # ── /expand ── #

    def do_expand(self):
        if not self._last_result:
            print_info(self._console, "ℹ  Nothing to expand yet")
            return
        print_full_result(self._console, self._last_result, self._last_tool)

    # ── /history ── #

    def do_history(self):
        print_history(self._console, self._steps)

    # ── /clear ── #

    def do_clear(self, agent=None):
        animated_clear(self._console)
        if agent:
            agent.clear()
        self._session_start = datetime.now()
        self._steps.clear()
        self._last_result   = ""
        if self._status_bar:
            self._status_bar.print()
        print_success_line(self._console,
                           "Conversation cleared  ·  Ready for new task")

    # ── /compact (LLM-based) ── #

    def do_compact(self, agent=None):
        if not agent:
            print_info(self._console, "No agent available")
            return

        from context.compression import ContextCompressor
        compressor = ContextCompressor()
        old_tokens = compressor._count_tokens(agent.messages)

        if len(agent.messages) <= 4:
            print_info(self._console, "Nothing to compact")
            return

        # Try LLM-based summarisation
        with Live(
            Spinner("dots", text=Text(
                "  Compressing conversation history...", style=C["cyan"]
            )),
            console=self._console,
            refresh_per_second=15,
            transient=True,
        ):
            try:
                summary = self._llm_summarise(agent.messages)
            except Exception:
                summary = None

        if summary:
            from core.agent import SYSTEM_PROMPT
            agent.messages = [
                {"role": "system",  "content": SYSTEM_PROMPT},
                {"role": "user",    "content": f"Previous session summary:\n{summary}"},
                {"role": "assistant", "content": "Understood. Continuing from the summary.", "tool_calls": []},
            ]
        else:
            agent.messages = compressor.compress(agent.messages, target_tokens=30000)

        new_tokens = compressor._count_tokens(agent.messages)
        saved_pct  = int((1 - new_tokens / max(old_tokens, 1)) * 100)
        print_success_line(self._console,
            f"Compressed: {old_tokens:,} → {new_tokens:,} tokens  (saved {saved_pct}%)")

    def _llm_summarise(self, messages: list) -> Optional[str]:
        from llm_model import call_model_stream
        history_text = []
        for m in messages:
            role = m.get("role", "")
            if role == "system":
                continue
            if role == "user":
                history_text.append(f"User: {m.get('content','')}")
            elif role == "assistant":
                if m.get("content"):
                    history_text.append(f"Agent: {m.get('content','')}")
                for tc in m.get("tool_calls", []):
                    name = tc.name if hasattr(tc, "name") else tc.get("name","")
                    history_text.append(f"[tool] {name}")
            elif role == "tool_result":
                for tr in m.get("results", []):
                    history_text.append(f"[result] {str(tr.get('content',''))[:100]}")

        prompt = (
            "Summarize this conversation history in 3-5 sentences, "
            "keeping all important context, file names, decisions made, "
            "and current task status. Be concise.\n\n"
            + "\n".join(history_text[-60:])
        )
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user",   "content": prompt},
        ]
        result = ""
        for chunk in call_model_stream(msgs, []):
            if chunk.type == "text":
                result += chunk.content
        return result.strip() or None

    # ── /mcp submenu ── #

    async def do_mcp_submenu(self, input_handler):
        w = min(self._console.width, 80)
        top = "┌" + "─" * (w - 2) + "┐"
        mid = "├" + "─" * 4 + "┬" + "─" * (w - 7) + "┤"
        bot = "└" + "─" * (w - 2) + "┘"

        def hdr(text):
            pad = w - 4 - len(text)
            self._console.print(f"│  {text}{' ' * max(pad,0)}  │",
                                 style=f"bold {C['white']}")

        def opt(num, desc):
            t = Text()
            t.append("│ ", style=f"dim {C['gray']}")
            t.append(f" {num} ", style=f"bold {C['cyan']}")
            t.append("│  ", style=f"dim {C['gray']}")
            pad = w - 7 - len(desc)
            t.append(desc, style=C["white"])
            t.append(" " * max(pad, 0) + "│", style=f"dim {C['gray']}")
            self._console.print(t)

        while True:
            self._console.print()
            self._console.print(top, style=f"dim {C['gray']}")
            hdr("MCP SERVER MANAGER")
            self._console.print(mid, style=f"dim {C['gray']}")
            opt("1", "List connected servers")
            opt("2", "Show server tools")
            opt("3", "Restart server")
            opt("4", "Server health check")
            opt("0", "Back to main")
            self._console.print(bot, style=f"dim {C['gray']}")

            choice = await input_handler.prompt_sub_async("mcp")
            if choice is None or choice == "0":
                break

            if choice == "1":
                self._mcp_list_servers()
            elif choice == "2":
                await self._mcp_show_tools()
            elif choice == "3":
                self._mcp_restart()
            elif choice == "4":
                self._mcp_health()
            else:
                print_info(self._console, f"Unknown option: {choice}")

    def _mcp_list_servers(self):
        try:
            from core.mcp_manager import load_mcp_config
            config  = load_mcp_config()
            servers = config.get("mcpServers", {})
            if not servers:
                print_info(self._console, "No servers configured")
                return
            print_mcp_servers(self._console, servers)
        except Exception as e:
            print_error(self._console, str(e))

    async def _mcp_show_tools(self):
        import asyncio
        import socket

        def _is_running():
            try:
                s = socket.create_connection(("localhost", 8000), timeout=1)
                s.close()
                return True
            except Exception:
                return False

        if not _is_running():
            print_info(self._console, "MCP server not running")
            return

        try:
            from core.mcp_manager import MCPManager
            m = MCPManager()
            await m.connect(silent=True)
            tools = m.get_tool_definitions()
            await m.disconnect()
            from rich.table import Table
            table = Table(border_style=C["gray_dark"], show_header=True,
                          header_style=f"bold {C['cyan']}",
                          title=f"[bold {C['white']}]Available Tools[/]")
            table.add_column("Tool",        style=f"bold {C['cyan']}")
            table.add_column("Description", style=C["white"])
            for t in tools:
                desc = (t.get("description") or "")[:60]
                table.add_row(t.get("name", ""), desc)
            self._console.print()
            self._console.print(table)
        except Exception as e:
            print_error(self._console, str(e))

    def _mcp_restart(self):
        import subprocess, sys, time, socket
        print_info(self._console, "Restarting MCP server...")
        # Kill existing
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if "mcp_server.py" in cmdline:
                    proc.terminate()
        except Exception:
            pass

        script = os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), "mcp_server.py")
        if not os.path.isfile(script):
            print_error(self._console, "mcp_server.py not found")
            return

        proc = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(20):
            time.sleep(0.5)
            try:
                s = socket.create_connection(("localhost", 8000), timeout=1)
                s.close()
                print_success_line(self._console, "MCP server restarted")
                return
            except Exception:
                pass
        print_error(self._console, "MCP server failed to start")

    def _mcp_health(self):
        import socket, time
        host, port = "localhost", 8000
        t0 = time.time()
        try:
            s  = socket.create_connection((host, port), timeout=3)
            ms = int((time.time() - t0) * 1000)
            s.close()
            print_success_line(self._console, f"MCP server healthy  ·  {ms}ms response time")
        except Exception as e:
            print_error(self._console, f"MCP server unreachable: {e}")

    # ── /model submenu ── #

    async def do_model_submenu(self, input_handler, agent=None):
        from llm_model import get_active_backend, NVIDIA_MODEL, DEPLOYMENT_ID

        def _current_model_display():
            backend = get_active_backend()
            nv = NVIDIA_MODEL.split("/")[-1] if "/" in NVIDIA_MODEL else NVIDIA_MODEL
            if backend == "sap":
                dep = DEPLOYMENT_ID[:12] + "…" if len(DEPLOYMENT_ID) > 12 else DEPLOYMENT_ID
                return f"SAP ({dep})" if DEPLOYMENT_ID else "SAP"
            elif backend == "nvidia":
                return nv
            else:
                return f"auto → {nv}"
        w = min(self._console.width, 80)
        top = "┌" + "─" * (w - 2) + "┐"
        mid = "├" + "─" * 4 + "┬" + "─" * (w - 7) + "┤"
        bot = "└" + "─" * (w - 2) + "┘"

        def hdr(text):
            pad = w - 4 - len(text)
            self._console.print(f"│  {text}{' ' * max(pad,0)}  │",
                                 style=f"bold {C['white']}")

        def opt(num, desc):
            t = Text()
            t.append("│ ", style=f"dim {C['gray']}")
            t.append(f" {num} ", style=f"bold {C['cyan']}")
            t.append("│  ", style=f"dim {C['gray']}")
            pad = w - 7 - len(desc)
            t.append(desc, style=C["white"])
            t.append(" " * max(pad, 0) + "│", style=f"dim {C['gray']}")
            self._console.print(t)

        while True:
            cur_model   = _current_model_display()
            cur_backend = get_active_backend()

            self._console.print()
            self._console.print(top, style=f"dim {C['gray']}")
            hdr(f"MODEL MANAGER  ·  current: {cur_model}")
            self._console.print(mid, style=f"dim {C['gray']}")
            opt("1", "Show current model details")
            opt("2", "Switch backend  (sap / nvidia / auto)")
            opt("0", "Back")
            self._console.print(bot, style=f"dim {C['gray']}")

            choice = await input_handler.prompt_sub_async("model")
            if choice is None or choice == "0":
                break

            if choice == "1":
                self._console.print()
                t = Text("  ")
                t.append("model   ", style=f"dim {C['gray']}")
                t.append(cur_model, style=f"bold {C['cyan']}")
                t.append("\n  backend  ", style=f"dim {C['gray']}")
                t.append(cur_backend, style=C["cyan"])
                t.append(f"\n  tokens   ", style=f"dim {C['gray']}")
                t.append(f"{self._total_tokens:,}", style=C["white"])
                t.append(" this session", style=f"dim {C['gray']}")
                self._console.print(t)

            elif choice == "2":
                new_backend = await input_handler.prompt_plain_async("  Enter backend (sap/nvidia/auto)")
                if new_backend and new_backend.lower() in ("sap", "nvidia", "auto"):
                    if agent:
                        agent.set_model(new_backend.lower())
                    new_display = _current_model_display()
                    if self._status_bar:
                        self._status_bar.set_model(new_display, new_backend.lower())
                    print_success_line(self._console,
                        f"Backend switched to {new_backend.lower()}  ·  {new_display}")
                    self._model   = new_display
                    self._backend = new_backend.lower()
                elif new_backend:
                    print_warning(self._console, f"Unknown backend: {new_backend}")
            else:
                print_info(self._console, f"Unknown option: {choice}")

    # ── File created dialog ── #

    def show_files_created_dialog(self, files: list) -> list:
        """Returns list of files to DELETE (empty = keep all)."""
        if not files:
            return []
        ans = print_files_created(self._console, files)
        if not ans or ans in ("y", "keep", "yes"):
            return []
        if ans == "n":
            return [path for path, _ in files]
        if ans == "select":
            numbered = input_handler.prompt_plain(
                "  Enter numbers to delete (e.g. 1,3): "
            )
            if not numbered:
                return []
            to_delete = []
            for part in numbered.split(","):
                part = part.strip()
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < len(files):
                        to_delete.append(files[idx][0])
            return to_delete
        return []

    # ── Goodbye + session save ── #

    def print_goodbye(self):
        self._console.print()
        print_info(self._console, "Goodbye!")
        self._console.print()


# ── Module-level singletons ── #
neural_ui     = NeuralUI()
input_handler = InputHandler()

# Wire ESC ESC cancel callback
input_handler.set_cancel_callback(neural_ui.stop_current)
