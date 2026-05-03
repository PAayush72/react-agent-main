# ui/components.py — All visual blocks: user, thought, action, observation, answer, status

import shutil
import sys
import threading
import time
from datetime import datetime
from typing import Any, Optional

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from ui.colors import C
from ui.formatters import auto_format_result, _step_prefix, _EXT_LANG


def _width() -> int:
    return min(shutil.get_terminal_size((80, 24)).columns - 2, 90)


def _console_width(console: Console) -> int:
    return min(console.width - 2, 90)


# ───────────────── STATUS BAR ───────────────── #

class StatusBar:
    def __init__(self, console: Console, model: str, backend: str, cwd: str):
        self._console  = console
        self._model    = model
        self._backend  = backend
        self._cwd      = cwd
        self._tokens   = 0
        self._calls    = 0
        self._start    = datetime.now()

    def _elapsed(self) -> str:
        delta = datetime.now() - self._start
        m, s  = divmod(int(delta.total_seconds()), 60)
        return f"{m:02d}:{s:02d}"

    def set_model(self, model: str, backend: str):
        self._model   = model
        self._backend = backend

    def render(self) -> Text:
        t = Text()
        t.append(" ⚡ NEURAL", style=f"bold {C['cyan']}")
        t.append("  ·  ", style=f"dim {C['gray']}")
        t.append(self._model, style=C["cyan"])
        t.append("  ·  ", style=f"dim {C['gray']}")
        t.append(self._backend, style=f"dim {C['white_dim']}")
        t.append("  ·  ", style=f"dim {C['gray']}")
        t.append(self._cwd, style=C["yellow"])
        t.append("\n ◈ tokens: ", style=f"dim {C['gray']}")
        t.append(f"{self._tokens:,}", style=C["white"])
        t.append("  ·  ◈ calls: ", style=f"dim {C['gray']}")
        t.append(str(self._calls), style=C["white"])
        t.append("  ·  ◈ session: ", style=f"dim {C['gray']}")
        t.append(self._elapsed(), style=C["white"])
        return t

    def print(self):
        w = min(self._console.width, 100)
        self._console.print(Panel(
            self.render(),
            border_style=C["gray_dark"],
            padding=(0, 1),
            width=w,
        ))

    def update(self, tokens: int = 0, calls: int = 0):
        self._tokens += tokens
        self._calls  += calls


# ───────────────── USER MESSAGE ───────────────── #

def print_user_message(console: Console, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"  [dim {C['gray']}]{ts}[/]")


# ───────────────── THINKING INDICATOR ───────────────── #

class ThinkingIndicator:
    def __init__(self, console: Console):
        self._console = console
        self._text    = "thinking"
        self._frames  = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self._idx     = 0
        self._active  = False
        self._thread  = None
        self._stop    = threading.Event()

    def start(self, text: str = "thinking"):
        self._text   = text
        self._active = True
        self._idx    = 0
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, text: str):
        self._text = text

    def stop(self):
        if self._active:
            self._active = False
            self._stop.set()
            if self._thread:
                self._thread.join(timeout=0.5)
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()

    def tick(self):
        pass

    def _run(self):
        while not self._stop.wait(0.1):
            frame = self._frames[self._idx % len(self._frames)]
            self._idx += 1
            sys.stdout.write(f"\r\033[2K  \033[36m{frame}\033[0m  \033[36mthinking\033[0m  \033[2m{self._text}\033[0m")
            sys.stdout.flush()
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()


# ───────────────── THOUGHT BLOCK ───────────────── #

class ThoughtBlock:
    def __init__(self, console: Console):
        self._console = console
        self._buf     = ""
        self._step    = 0
        self._started = False

    def begin(self, step: int = 0):
        self._buf     = ""
        self._step    = step
        self._started = False

    def stream_token(self, token: str):
        if not self._started:
            self._console.print()
            step_tag = _step_prefix(self._step)
            self._console.print(
                f"{step_tag}💭 ", end="", style=f"bold {C['purple']}"
            )
            self._started = True
        self._buf += token
        self._console.print(token, end="", style=f"italic {C['purple']}")
        self._console.file.flush()

    def end(self):
        if self._started:
            self._console.print()
            self._started = False

    def get_text(self) -> str:
        return self._buf


# ───────────────── ACTION BLOCK ───────────────── #

def print_action(console: Console, tool_name: str, args: dict, step: int = 0):
    step_tag = _step_prefix(step)
    w = _console_width(console) - 4

    console.print()
    console.print(f"{'─' * w}", style=f"dim {C['gray_dark']}")

    t = Text()
    t.append(f"  {step_tag}", style="")
    t.append("⟶  ", style=f"bold {C['cyan']}")
    t.append(tool_name, style=f"bold {C['cyan']}")
    console.print(t)

    display_args = {k: v for k, v in args.items() if k != "content"}

    keys = list(display_args.keys())
    for i, key in enumerate(keys):
        val = display_args[key]
        is_last = (i == len(keys) - 1) and "content" not in args
        connector = "└─" if is_last else "├─"

        val_str = str(val)
        if len(val_str) > 60:
            val_str = val_str[:57] + "..."

        row = Text()
        row.append(f"     {connector} ", style=f"dim {C['gray']}")
        row.append(f"{key}", style=f"dim {C['gray_light']}")
        row.append("  ", style="")
        row.append(val_str, style=C["white"])
        console.print(row)

    if "content" in args:
        lines = str(args["content"]).count("\n") + 1
        row = Text()
        row.append("     └─ ", style=f"dim {C['gray']}")
        row.append("content", style=f"dim {C['gray_light']}")
        row.append(f"  [{lines} lines]", style=f"dim {C['white_dim']}")
        console.print(row)

    console.print(f"{'─' * w}", style=f"dim {C['gray_dark']}")


# ───────────────── OBSERVATION BLOCK ───────────────── #

def print_observation(console: Console, result: str,
                      tool_name: str = "", step: int = 0):
    if not result or not result.strip():
        return
    console.print()
    auto_format_result(result, console, tool_name=tool_name, step=step)


# ───────────────── ANSWER BLOCK (BUG1+BUG3 fixed) ───────────────── #

def print_answer(console: Console, text: str,
                 tool_calls: int = 0, tokens: int = 0, elapsed: float = 0.0):
    w = console.width - 4

    top   = "╔" + "═" * (w - 2) + "╗"
    sep   = "╠" + "═" * (w - 2) + "╣"
    bot   = "╚" + "═" * (w - 2) + "╝"

    inner_w = w - 6

    def row(content: str, style: str = C["white"]) -> Text:
        import textwrap as _tw
        wrapped = _tw.wrap(content, width=inner_w) or [""]
        result_text = Text()
        for i, wline in enumerate(wrapped):
            pad = inner_w - len(wline)
            result_text.append("║  ", style=f"dim {C['green']}")
            result_text.append(wline, style=style)
            result_text.append(" " * max(pad, 0) + "  ║", style=f"dim {C['green']}")
            if i < len(wrapped) - 1:
                result_text.append("\n")
        return result_text

    stats = (f"{tool_calls} tool call{'s' if tool_calls != 1 else ''}"
             f"  ·  {tokens:,} tokens  ·  took {elapsed:.1f}s")

    console.print()
    console.print(top, style=f"bold {C['green']}")
    console.print(row("✓  Complete", style=f"bold {C['green']}"))
    console.print(sep, style=f"dim {C['green']}")
    console.print(row(stats, style=f"dim {C['gray_light']}"))
    console.print(bot, style=f"bold {C['green']}")
    console.print()


# ───────────────── EXPAND: full result display ───────────────── #

def print_full_result(console: Console, text: str, tool_name: str = ""):
    if not text:
        print_info(console, "Nothing to expand yet")
        return
    console.print()
    # Detect language for syntax highlighting
    import re, os
    filename = ""
    first_line = text.splitlines()[0] if text.splitlines() else ""
    m = re.match(r"^(.+\.\w+)\s+\(", first_line)
    if m:
        filename = m.group(1).strip()
    ext  = os.path.splitext(filename)[1].lower()
    lang = _EXT_LANG.get(ext, "text")
    try:
        syn = Syntax(text, lang, theme="monokai", line_numbers=True,
                     background_color="default", word_wrap=True)
        console.print(Panel(syn,
                            title=f"[dim {C['gray']}]expand · {filename or tool_name}[/]",
                            border_style=C["cyan"],
                            padding=(0, 1)))
    except Exception:
        console.print(Panel(Text(text, style=f"dim {C['white_dim']}"),
                            title=f"[dim {C['gray']}]expand[/]",
                            border_style=C["cyan"],
                            padding=(0, 1)))


# ───────────────── HISTORY TABLE ───────────────── #

def print_history(console: Console, steps: list):
    if not steps:
        print_info(console, "No steps recorded this session")
        return

    table = Table(
        border_style=C["gray_dark"],
        show_header=True,
        header_style=f"bold {C['cyan']}",
        title=f"[bold {C['white']}]Session History[/]",
        padding=(0, 1),
    )
    table.add_column("#",       style=f"dim {C['gray']}",  width=4,  no_wrap=True)
    table.add_column("Type",    style=C["cyan"],            width=9,  no_wrap=True)
    table.add_column("Summary", style=C["white"])

    for entry in steps:
        step_n = str(entry.get("step", ""))
        etype  = entry.get("type", "")
        summ   = entry.get("summary", "")
        if len(summ) > 60:
            summ = summ[:57] + "..."
        color_map = {
            "thought": C["purple"],
            "action":  C["cyan"],
            "observe": C["green"],
            "answer":  C["white"],
        }
        style = color_map.get(etype, C["white"])
        table.add_row(step_n, etype,
                      Text(summ, style=style))

    console.print()
    console.print(table)
    console.print()


# ───────────────── CLEAR ANIMATION ───────────────── #

def animated_clear(console: Console):
    import sys
    h = shutil.get_terminal_size((80, 24)).lines
    for _ in range(min(h, 40)):
        console.print(" " * console.width, end="\r")
        time.sleep(0.008)
    console.clear()


# ───────────────── ERROR / WARNING / INFO ───────────────── #

def print_error(console: Console, message: str):
    console.print()
    console.print(Panel(
        Text(message, style=f"bold {C['red']}"),
        title=f"[bold {C['red']}]✗ Error[/]",
        border_style=C["red"],
        padding=(0, 1),
    ))


def print_warning(console: Console, message: str):
    t = Text()
    t.append("\n  ⚠  ", style=f"bold {C['amber']}")
    t.append(message, style=C["amber"])
    console.print(t)


def print_info(console: Console, message: str):
    t = Text()
    t.append("  ◌  ", style=f"dim {C['gray']}")
    t.append(message, style=f"dim {C['white_dim']}")
    console.print(t)


def print_success_line(console: Console, message: str):
    t = Text()
    t.append("  ✦  ", style=f"bold {C['green']}")
    t.append(message, style=C["green"])
    console.print(t)


def print_cancelled(console: Console):
    t = Text()
    t.append("\n  ⊘  Cancelled", style=f"bold {C['amber']}")
    console.print(t)


def print_stopped(console: Console, tokens: int = 0):
    t = Text()
    t.append("\n  ⊘  Stopped  ·  context saved", style=f"bold {C['amber']}")
    if tokens:
        t.append(f"  ·  {tokens:,} tokens preserved", style=C["amber"])
    console.print(t)


def print_loop_error(console: Console, message: str):
    t = Text()
    t.append("\n  !  ", style=f"bold {C['red']}")
    t.append(message, style=C["red"])
    console.print(t)


def print_step_indicator(console: Console, step: int, max_steps: int):
    console.print()
    console.print(
        f"  [dim {C['gray']}]─── step {step}/{max_steps} ───[/]"
    )


def print_tokens(console: Console, inp: int, out: int,
                 elapsed: float, model: str = ""):
    t = Text("  ")
    if model:
        t.append(model, style=f"bold {C['purple_dim']}")
        t.append("  │  ", style=f"dim {C['gray']}")
    t.append(f"in:{inp:,}", style=C["cyan_dim"])
    t.append("  ", style="")
    t.append(f"out:{out:,}", style=C["green_dim"])
    t.append("  │  ", style=f"dim {C['gray']}")
    t.append(f"{elapsed:.1f}s", style=f"dim {C['gray']}")
    console.print(t)


def print_first_token(console: Console, elapsed: float):
    console.print(f"  [dim {C['gray']}]first token in {elapsed:.1f}s[/]")
    console.print()


def print_permission_prompt(console: Console, tool_name: str, params: dict) -> bool:
    key_val = ""
    for k in ("path", "command", "query"):
        if k in params:
            key_val = f"  {k}={str(params[k])[:50]}"
            break
    try:
        ans = console.input(
            f"\n  [bold {C['amber']}]⚠  Allow[/] "
            f"[bold {C['cyan']}]{tool_name}[/]"
            f"[dim {C['gray']}]{key_val}[/] "
            f"[dim](y/n):[/] "
        )
        return ans.strip().lower() in ("y", "yes", "")
    except (EOFError, KeyboardInterrupt):
        return False


# ───────────────── HELP TABLE (with /expand /history /exit) ───────────────── #

def print_help(console: Console):
    w = _console_width(console)
    top  = "┌" + "─" * (w - 2) + "┐"
    mid  = "├" + "─" * 14 + "┬" + "─" * (w - 17) + "┤"
    bot  = "├" + "─" * 14 + "┴" + "─" * (w - 17) + "┤"
    end  = "└" + "─" * (w - 2) + "┘"

    def hdr_row(text: str) -> str:
        pad = w - 4 - len(text)
        return f"│  {text}{' ' * max(pad, 0)}  │"

    def cmd_row(cmd: str, desc: str) -> Text:
        t = Text()
        t.append("│  ", style=f"dim {C['gray']}")
        t.append(f"{cmd:<12}", style=f"bold {C['cyan']}")
        t.append("│  ", style=f"dim {C['gray']}")
        desc_pad = w - 17 - len(desc)
        t.append(desc, style=C["white"])
        t.append(" " * max(desc_pad, 0))
        t.append("│", style=f"dim {C['gray']}")
        return t

    console.print()
    console.print(top, style=f"dim {C['gray']}")
    console.print(hdr_row("NEURAL TERMINAL  ·  Command Reference"),
                  style=f"bold {C['white']}")
    console.print(mid, style=f"dim {C['gray']}")

    commands = [
        ("/help",    "Show this reference"),
        ("/clear",   "Clear screen and reset conversation"),
        ("/compact", "Compress history to save tokens"),
        ("/tokens",  "Show detailed token usage breakdown"),
        ("/model",   "Show or switch current model (submenu)"),
        ("/mcp",     "Manage MCP servers (submenu)"),
        ("/expand",  "Show full content of last truncated result"),
        ("/history", "Show all steps from this session"),
        ("/quit",    "Exit cleanly"),
        ("/exit",    "Alias for /quit"),
    ]
    for cmd, desc in commands:
        console.print(cmd_row(cmd, desc))

    console.print(bot, style=f"dim {C['gray']}")

    caps = "  Code · Charts · Diagrams · Docs · Notebooks · Web Search · News"
    console.print(hdr_row(caps), style=f"dim {C['cyan']}")
    footer = "  Ctrl+C  cancel task    ESC ESC  stop generation    Ctrl+D  exit"
    console.print(hdr_row(footer), style=f"dim {C['gray_light']}")
    console.print(end, style=f"dim {C['gray']}")
    console.print()


# ───────────────── TOKEN STATS TABLE (fixed progress bars) ───────────────── #

def _bar(fraction: float, width: int = 10) -> str:
    filled = int(round(fraction * width))
    return "█" * filled + "░" * (width - filled)


def print_token_stats(console: Console, stats: dict, session_start: datetime):
    inp  = stats.get("input_tokens", 0)
    out  = stats.get("output_tokens", 0)
    tot  = stats.get("total_tokens", 0)
    reqs = stats.get("steps", 0)

    delta = datetime.now() - session_start
    m, s  = divmod(int(delta.total_seconds()), 60)
    sess  = f"{m:02d}:{s:02d}"

    total_for_pct = max(tot, 1)
    ip = inp / total_for_pct
    op = out / total_for_pct

    w   = _console_width(console)
    # Column widths: label=21, value=13, bar=rest
    col1, col2 = 21, 13
    col3 = max(w - col1 - col2 - 7, 20)

    top     = "┌" + "─" * (w - 2) + "┐"
    mid     = "├" + "─" * col1 + "┬" + "─" * col2 + "┬" + "─" * col3 + "┤"
    sep_row = "├" + "─" * col1 + "┼" + "─" * col2 + "┼" + "─" * col3 + "┤"
    bot     = "└" + "─" * (w - 2) + "┘"

    def hdr_row(text: str):
        pad = w - 4 - len(text)
        console.print(f"│  {text}{' ' * max(pad, 0)}  │",
                      style=f"bold {C['white']}")

    def data_row(label: str, value: str, bar: str = ""):
        t = Text()
        t.append("│ ", style=f"dim {C['gray']}")
        t.append(f"{label:<{col1-1}}", style=C["white_dim"])
        t.append("│ ", style=f"dim {C['gray']}")
        t.append(f"{value:>{col2-1}}", style=f"bold {C['white']}")
        t.append("│ ", style=f"dim {C['gray']}")
        bar_pad = col3 - 1 - len(bar)
        t.append(bar, style=C["cyan"])
        t.append(" " * max(bar_pad, 0))
        t.append("│", style=f"dim {C['gray']}")
        console.print(t)

    console.print()
    console.print(top, style=f"dim {C['gray']}")
    hdr_row("TOKEN USAGE  ·  This Session")
    console.print(mid, style=f"dim {C['gray']}")
    data_row("Prompt tokens",     f"{inp:,}",  _bar(ip) + f"  {int(ip*100)}%")
    data_row("Completion tokens", f"{out:,}",  _bar(op) + f"  {int(op*100)}%")
    console.print(sep_row, style=f"dim {C['gray']}")
    data_row("Total",             f"{tot:,}",  "")
    console.print(sep_row, style=f"dim {C['gray']}")
    data_row("Requests made",     str(reqs),   "")
    data_row("Session time",      sess,        "")
    console.print(bot, style=f"dim {C['gray']}")
    console.print()


# ───────────────── MCP TABLE ───────────────── #

def print_mcp_servers(console: Console, servers: dict):
    table = Table(
        border_style=C["gray_dark"],
        show_header=True,
        header_style=f"bold {C['cyan']}",
        title=f"[bold {C['white']}]MCP Servers[/]",
    )
    table.add_column("Name",     style=C["white"])
    table.add_column("Type",     style=C["green"])
    table.add_column("Status",   style=C["cyan"])
    table.add_column("Endpoint", style=f"dim {C['gray_light']}")

    for name, cfg in servers.items():
        if name.startswith("_"):
            continue
        stype    = "HTTP"  if "url" in cfg else "STDIO" if "command" in cfg else "?"
        endpoint = cfg.get("url") or f"{cfg.get('command','')} {' '.join(cfg.get('args',[]))}"
        endpoint = (endpoint[:45] + "...") if len(endpoint) > 45 else endpoint
        status   = "[green]enabled[/]" if cfg.get("enabled", True) else "[red]disabled[/]"
        table.add_row(name, stype, status, endpoint)

    console.print()
    console.print(table)
    console.print()


# ───────────────── FILE SAVE DIALOG ───────────────── #

def print_files_created(console: Console, files: list) -> str:
    if not files:
        return "keep"

    w = _console_width(console)
    top = "┌" + "─" * (w - 2) + "┐"
    bot = "└" + "─" * (w - 2) + "┘"
    sep = "├" + "─" * (w - 2) + "┤"

    def hdr_row(text: str):
        pad = w - 4 - len(text)
        console.print(f"│  {text}{' ' * max(pad,0)}  │",
                      style=f"bold {C['white']}")

    def file_row(idx: int, path: str, lines: int):
        entry = f"  {idx}.  {path:<40}  ({lines} lines)"
        pad   = w - 4 - len(entry)
        console.print(f"│{entry}{' ' * max(pad,0)}  │",
                      style=C["white"])

    console.print()
    console.print(top, style=f"dim {C['gray']}")
    hdr_row("📁  Files Created This Session")
    console.print(sep, style=f"dim {C['gray']}")

    for i, (path, line_count) in enumerate(files, 1):
        file_row(i, path, line_count)

    console.print(sep, style=f"dim {C['gray']}")

    prompt_text = "  Keep these files? [Y/n/select]  ❯ "
    pad = w - 4 - len(prompt_text)
    console.print(f"│{prompt_text}{' ' * max(pad,0)}  │",
                  style=f"bold {C['cyan']}")
    console.print(bot, style=f"dim {C['gray']}")

    try:
        ans = console.input(
            f"  [bold {C['cyan']}]Keep files? [Y/n/select] ❯ [/]"
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "keep"

    return ans or "keep"
