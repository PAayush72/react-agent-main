# ui.py — Full TUI layer for ReAct Coding Agent
# Provides AgentUI (rendering) and InputHandler (prompt_toolkit input)
#
# NOTE: This root-level file is a legacy predecessor of the ui/ package.
# The active code lives in ui/__init__.py (and ui/*.py).
# This file is kept for reference only and is NOT imported by main.py.

import os
import re
import sys
import time
import threading
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.theme import Theme
from rich.markup import escape
from rich.columns import Columns

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.styles import Style as PTStyle

# ───────────────── COLOR SCHEME ───────────────── #

COLORS = {
    "primary":   "#00AFFF",   # bright cyan  — actions, tool calls
    "success":   "#00D700",   # bright green — success, observations
    "error":     "#FF5555",   # red          — errors
    "warning":   "#FFAF00",   # amber        — warnings
    "dim":       "#626262",   # gray         — secondary info, args
    "thought":   "#AF87FF",   # purple       — thoughts
    "answer":    "#E8E8E8",   # white        — final answer
    "filepath":  "#00AFFF",   # cyan         — file paths
    "separator": "#303030",   # dark gray    — rule lines
    "badge_bg":  "#1A1A2E",   # dark blue    — badge backgrounds
    "tool_name": "#00CFCF",   # teal         — tool names
    "result":    "#3A3A3A",   # dark         — result box border
    "user":      "#5C7CFA",   # indigo       — user label
    "accent":    "#A78BFA",   # violet       — accents
    "muted":     "#555555",   # dark gray    — muted text
}

_THEME = Theme({
    "primary":    COLORS["primary"],
    "success":    f"bold {COLORS['success']}",
    "error":      f"bold {COLORS['error']}",
    "warning":    f"bold {COLORS['warning']}",
    "dim_text":   f"dim {COLORS['dim']}",
    "thought":    f"italic {COLORS['thought']}",
    "answer":     COLORS["answer"],
    "filepath":   f"bold {COLORS['filepath']}",
    "tool.name":  f"bold {COLORS['tool_name']}",
    "tool.border": COLORS["primary"],
    "result.border": COLORS["success"],
    "user.label": f"bold {COLORS['user']}",
    "accent":     COLORS["accent"],
    "muted":      COLORS["muted"],
    "step.label": f"bold {COLORS['primary']}",
})

console = Console(theme=_THEME, highlight=False)

# ───────────────── LANGUAGE DETECTION ───────────────── #

_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".html": "html", ".css": "css",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".md": "markdown", ".rs": "rust", ".go": "go",
    ".cpp": "cpp", ".c": "c", ".h": "c", ".java": "java",
    ".rb": "ruby", ".php": "php", ".sql": "sql", ".toml": "toml",
    ".xml": "xml", ".dockerfile": "dockerfile",
}

def _detect_language(path: str, content: str = "") -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _EXT_LANG:
        return _EXT_LANG[ext]
    if content.startswith("#!/"):
        first = content.splitlines()[0].lower()
        if "python" in first: return "python"
        if "bash" in first or "sh" in first: return "bash"
        if "node" in first: return "javascript"
    return "text"


def _looks_like_json(s: str) -> bool:
    s = s.strip()
    return (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))


def _highlight_filepaths(text: str) -> Text:
    """Return a Rich Text with file paths highlighted cyan."""
    result = Text()
    pattern = re.compile(r'([\w./\\-]+\.(?:py|js|ts|json|yaml|yml|md|txt|sh|html|css|go|rs|cpp|c|java|rb|php|sql|toml|xml|ipynb))')
    last = 0
    for m in pattern.finditer(text):
        result.append(text[last:m.start()])
        result.append(m.group(), style=f"bold {COLORS['filepath']}")
        last = m.end()
    result.append(text[last:])
    return result


# ───────────────── AGENT UI ───────────────── #

class AgentUI:
    """All terminal rendering for the ReAct agent."""

    def __init__(self):
        self._spinner_live: Optional[Live] = None
        self._spinner_lock = threading.Lock()

    # ── Header ── #

    def print_header(self, model: str = "", backend: str = "", cwd: str = ""):
        cwd = cwd or os.path.basename(os.getcwd()) + "/"
        model = model or "unknown"
        backend = backend or "auto"

        console.print()

        title_text = Text()
        title_text.append("  ⚡ ", style=f"bold {COLORS['accent']}")
        title_text.append("ReAct Coding Agent", style=f"bold {COLORS['answer']}")
        title_text.append("  ", style="")
        title_text.append(f"  {model}", style=f"{COLORS['accent']}")
        title_text.append("  │  ", style=f"dim {COLORS['muted']}")
        title_text.append(f"{backend}", style=f"{COLORS['primary']}")
        title_text.append("  │  ", style=f"dim {COLORS['muted']}")
        title_text.append(f"{cwd}", style=f"dim {COLORS['dim']}")

        console.print(Panel(
            title_text,
            border_style=COLORS["separator"],
            padding=(0, 1),
        ))

        keys = Text("  ")
        shortcuts = ["/help", "/clear", "/compact", "/tokens", "/model", "/mcp", "/quit"]
        for i, k in enumerate(shortcuts):
            if i:
                keys.append("  ")
            keys.append(k, style=f"bold {COLORS['dim']}")
        keys.append("    Ctrl+C", style=f"{COLORS['dim']}")
        keys.append(" cancel", style=f"dim {COLORS['muted']}")
        console.print(keys)
        console.print(Rule(style=COLORS["separator"]))
        console.print()

    # ── Spinner ── #

    def start_spinner(self, text: str = "Thinking..."):
        with self._spinner_lock:
            if self._spinner_live is not None:
                return
            spinner = Spinner("dots", text=f"  [accent]{text}[/]", style=f"{COLORS['accent']}")
            self._spinner_live = Live(spinner, console=console, refresh_per_second=12, transient=True)
            self._spinner_live.start()

    def update_spinner(self, text: str):
        with self._spinner_lock:
            if self._spinner_live is not None:
                spinner = Spinner("dots", text=f"  [accent]{text}[/]", style=f"{COLORS['accent']}")
                self._spinner_live.update(spinner)

    def stop_spinner(self):
        with self._spinner_lock:
            if self._spinner_live is not None:
                self._spinner_live.stop()
                self._spinner_live = None

    # ── Step types ── #

    def print_user_message(self, message: str):
        t = Text()
        t.append("  you  ", style=f"bold {COLORS['user']} on #1E2952")
        t.append(f"  {message}", style=f"{COLORS['answer']}")
        console.print()
        console.print(t)

    def print_thought(self, content: str):
        label = Text()
        label.append("  💭 Thought  ", style=f"bold {COLORS['thought']}")
        label.append(content, style=f"italic dim {COLORS['thought']}")
        console.print()
        console.print(label)

    def print_tool_call(self, name: str, params: dict):
        icon = "→"
        key_param = ""
        for k in ("path", "command", "query", "pattern", "url", "user_query", "spec"):
            if k in params:
                val = str(params[k])
                if len(val) > 72:
                    val = val[:69] + "..."
                key_param = val
                break

        t = Text()
        t.append(f"\n  {icon} ", style=f"bold {COLORS['primary']}")
        t.append(name, style=f"bold {COLORS['tool_name']}")
        if key_param:
            t.append("  ", style="")
            t.append(_highlight_filepaths(key_param))

        if name == "write_file" and "content" in params:
            lines = params["content"].count("\n") + 1
            t.append(f"  [{lines} lines]", style=f"dim {COLORS['dim']}")

        extra = {k: v for k, v in params.items()
                 if k not in ("path", "command", "query", "pattern", "url", "user_query", "spec", "content")}
        if extra:
            args_str = "  ".join(f"{k}={str(v)[:30]}" for k, v in list(extra.items())[:3])
            t.append(f"\n     {args_str}", style=f"dim {COLORS['dim']}")

        console.print(t)

    def print_tool_result(self, result: str, tool_name: str = ""):
        if not result or not result.strip():
            return

        MAX_LINES = 40
        lines = result.splitlines()
        truncated = len(lines) > MAX_LINES
        display_lines = lines[:MAX_LINES]
        display = "\n".join(display_lines)

        if truncated:
            display += f"\n  [dim]... ({len(lines) - MAX_LINES} more lines)[/]"

        ext = ""
        if tool_name in ("read_file", "write_file", "patch_file"):
            first_line = lines[0] if lines else ""
            m = re.search(r'\.(\w+)\s', first_line)
            if m:
                ext = "." + m.group(1)

        lang = _EXT_LANG.get(ext, "")

        if lang and len(lines) > 3:
            try:
                syn = Syntax(display, lang, theme="monokai", line_numbers=False,
                             background_color="default", word_wrap=False)
                console.print(Panel(syn, border_style=COLORS["result"],
                                    title=f"[dim_text]◉ result[/]", padding=(0, 1)))
                return
            except Exception:
                pass

        if _looks_like_json(display):
            try:
                syn = Syntax(display, "json", theme="monokai", line_numbers=False,
                             background_color="default")
                console.print(Panel(syn, border_style=COLORS["result"],
                                    title=f"[dim_text]◉ result[/]", padding=(0, 1)))
                return
            except Exception:
                pass

        content_text = Text.from_markup(f"[dim {COLORS['answer']}]{escape(display)}[/]")
        console.print(Panel(content_text, border_style=COLORS["result"],
                            title=f"[dim_text]◉ result[/]", padding=(0, 1)))

    def print_code(self, code: str, language: str = "python", title: str = ""):
        syn = Syntax(code, language, theme="monokai", line_numbers=True,
                     background_color="default", word_wrap=False)
        panel_title = f"[filepath]{title}[/]" if title else f"[dim_text]{language}[/]"
        console.print(Panel(syn, title=panel_title, border_style=COLORS["primary"],
                            padding=(0, 1)))

    def print_diff(self, diff_text: str):
        lines = diff_text.splitlines()
        out = Text()
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                out.append(line + "\n", style=f"bold {COLORS['success']}")
            elif line.startswith("-") and not line.startswith("---"):
                out.append(line + "\n", style=f"bold {COLORS['error']}")
            elif line.startswith("@@"):
                out.append(line + "\n", style=f"bold {COLORS['primary']}")
            elif line.startswith("---") or line.startswith("+++"):
                out.append(line + "\n", style=f"dim {COLORS['dim']}")
            else:
                out.append(line + "\n", style=f"dim {COLORS['answer']}")
        console.print(Panel(out, title="[dim_text]diff[/]",
                            border_style=COLORS["dim"], padding=(0, 1)))

    def print_answer(self, content: str):
        if not content.strip():
            return
        console.print()
        md_text = Text.from_markup(f"[answer]{escape(content)}[/]")
        console.print(md_text)

    def print_error(self, message: str):
        console.print()
        console.print(Panel(
            Text(message, style=f"bold {COLORS['error']}"),
            title=f"[error]✗ Error[/]",
            border_style=COLORS["error"],
            padding=(0, 1),
        ))

    def print_success(self, message: str):
        console.print()
        console.print(Panel(
            Text(message, style=COLORS["success"]),
            title=f"[success]✓ Done[/]",
            border_style=COLORS["success"],
            padding=(0, 1),
        ))

    def print_warning(self, message: str):
        t = Text()
        t.append("  ⚠  ", style=f"bold {COLORS['warning']}")
        t.append(message, style=COLORS["warning"])
        console.print(t)

    def print_info(self, message: str):
        t = Text()
        t.append("  ◌  ", style=f"{COLORS['dim']}")
        t.append(message, style=f"dim {COLORS['answer']}")
        console.print(t)

    def print_mcp_ready(self, success: bool, message: str = ""):
        if success:
            t = Text()
            t.append("  ✓  ", style=f"bold {COLORS['success']}")
            t.append(message or "MCP server ready", style=COLORS["success"])
            console.print(t)
        else:
            t = Text()
            t.append("  ✗  ", style=f"bold {COLORS['error']}")
            t.append(message or "MCP server failed", style=COLORS["error"])
            console.print(t)

    def print_step_indicator(self, step: int, max_steps: int):
        console.print()
        console.print(f"  [muted]─── step {step}/{max_steps} ───[/]")

    def print_tokens(self, input_tokens: int, output_tokens: int, elapsed: float,
                     model: str = ""):
        t = Text("  ")
        if model:
            t.append(f"{model}", style=f"bold {COLORS['accent']}")
            t.append("  │  ", style=f"dim {COLORS['muted']}")
        t.append(f"in:{input_tokens:,}", style=COLORS["primary"])
        t.append("  ", style="")
        t.append(f"out:{output_tokens:,}", style=COLORS["success"])
        t.append("  │  ", style=f"dim {COLORS['muted']}")
        t.append(f"{elapsed:.1f}s", style=f"dim {COLORS['dim']}")
        console.print(t)

    def print_first_token(self, elapsed: float):
        console.print(f"  [muted]first token in {elapsed:.1f}s[/]")
        console.print()

    def print_loop_error(self, message: str):
        t = Text()
        t.append("\n  ! ", style=f"bold {COLORS['error']}")
        t.append(message, style=COLORS["error"])
        console.print(t)

    def print_permission_prompt(self, tool_name: str, params: dict) -> bool:
        key_val = ""
        for k in ("path", "command", "query"):
            if k in params:
                key_val = f"  {k}={str(params[k])[:50]}"
                break
        prompt_text = (
            f"\n  [warning]⚠  Allow[/] [tool.name]{tool_name}[/]"
            f"[dim_text]{escape(key_val)}[/] [dim](y/n):[/] "
        )
        if not sys.stdin.isatty():
            return True
        try:
            ans = console.input(prompt_text)
            return ans.strip().lower() in ("y", "yes", "")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── Help ── #

    def print_help(self):
        table = Table(
            border_style=COLORS["separator"],
            show_header=True,
            header_style=f"bold {COLORS['accent']}",
            title=f"[bold {COLORS['answer']}]Commands[/]",
            padding=(0, 2),
        )
        table.add_column("Command", style=f"bold {COLORS['accent']}", no_wrap=True)
        table.add_column("Description", style=COLORS["answer"])

        rows = [
            ("/help",    "Show this help screen"),
            ("/clear",   "Clear conversation history and redraw header"),
            ("/compact", "Compress context to save tokens"),
            ("/tokens",  "Show token usage statistics"),
            ("/model",   "Show or switch model backend (sap / nvidia / auto)"),
            ("/mcp",     "Manage MCP server connections"),
            ("/quit",    "Exit the agent"),
        ]
        for cmd, desc in rows:
            table.add_row(cmd, desc)

        shortcuts = Table.grid(padding=(0, 4))
        shortcuts.add_row(
            Text("↑/↓", style=f"bold {COLORS['dim']}"),
            Text("Navigate history", style=f"dim {COLORS['dim']}"),
            Text("Ctrl+C", style=f"bold {COLORS['dim']}"),
            Text("Cancel current operation", style=f"dim {COLORS['dim']}"),
            Text("Ctrl+D", style=f"bold {COLORS['dim']}"),
            Text("Exit cleanly", style=f"dim {COLORS['dim']}"),
        )

        console.print()
        console.print(table)
        console.print()
        console.print(shortcuts)
        console.print()

    # ── Token stats table ── #

    def print_token_stats(self, stats: dict):
        table = Table(
            border_style=COLORS["separator"],
            show_header=True,
            header_style=f"bold {COLORS['accent']}",
            title=f"[bold {COLORS['answer']}]Token Usage[/]",
            padding=(0, 2),
        )
        table.add_column("Metric", style=COLORS["answer"])
        table.add_column("Value", style=f"bold {COLORS['success']}", justify="right")

        table.add_row("Steps taken",   str(stats.get("steps", 0)))
        table.add_row("Messages",      str(stats.get("messages", 0)))
        table.add_row("Input tokens",  f"{stats.get('input_tokens', 0):,}")
        table.add_row("Output tokens", f"{stats.get('output_tokens', 0):,}")
        table.add_row("Total tokens",  f"[bold]{stats.get('total_tokens', 0):,}[/]")

        console.print()
        console.print(table)
        console.print()

    # ── MCP server table ── #

    def print_mcp_servers(self, servers: dict):
        table = Table(
            border_style=COLORS["separator"],
            show_header=True,
            header_style=f"bold {COLORS['accent']}",
            title=f"[bold {COLORS['answer']}]MCP Servers[/]",
        )
        table.add_column("Name",   style=COLORS["answer"])
        table.add_column("Type",   style=COLORS["success"])
        table.add_column("Status", style=COLORS["primary"])
        table.add_column("Endpoint / Command", style=f"dim {COLORS['dim']}")

        for name, cfg in servers.items():
            if name.startswith("_"):
                continue
            stype = "HTTP" if "url" in cfg else "STDIO" if "command" in cfg else "?"
            endpoint = cfg.get("url") or f"{cfg.get('command', '')} {' '.join(cfg.get('args', []))}"
            endpoint = (endpoint[:50] + "...") if len(endpoint) > 50 else endpoint
            status = "[green]enabled[/]" if cfg.get("enabled", True) else "[red]disabled[/]"
            table.add_row(name, stype, status, endpoint)

        console.print()
        console.print(table)
        console.print()

    def print_model_info(self, model: str, backend: str):
        t = Text("  ")
        t.append("model  ", style=f"dim {COLORS['dim']}")
        t.append(model, style=f"bold {COLORS['accent']}")
        t.append("    backend  ", style=f"dim {COLORS['dim']}")
        t.append(backend, style=f"bold {COLORS['primary']}")
        console.print(t)
        console.print(f"  [dim {COLORS['dim']}]Usage: /model sap | nvidia | auto[/]")


# ───────────────── INPUT HANDLER ───────────────── #

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".react_agent_history")

SLASH_COMMANDS = WordCompleter(
    ["/help", "/clear", "/compact", "/quit", "/exit",
     "/tokens", "/model", "/cost", "/mcp"],
    sentence=True,
)

_PT_STYLE = PTStyle.from_dict({
    "prompt": f"bold fg:{COLORS['user']}",
})


class InputHandler:
    """Styled prompt_toolkit input with history and slash-command completion."""

    def __init__(self):
        self._session: Optional[PromptSession] = None

    def _get_session(self) -> PromptSession:
        if self._session is None:
            self._session = PromptSession(
                history=FileHistory(HISTORY_FILE),
                auto_suggest=AutoSuggestFromHistory(),
                completer=SLASH_COMMANDS,
                style=_PT_STYLE,
            )
        return self._session

    def prompt(self) -> Optional[str]:
        """Show the > prompt and return stripped input. None on EOF/interrupt."""
        try:
            raw = self._get_session().prompt(
                ANSI(f"\033[1;38;2;92;102;250m> \033[0m"),
            )
            return raw.strip() if raw else ""
        except EOFError:
            return None
        except KeyboardInterrupt:
            return ""


# ───────────────── MODULE-LEVEL SINGLETON ───────────────── #

ui = AgentUI()
input_handler = InputHandler()
