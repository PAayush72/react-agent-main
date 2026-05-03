# ui/animations.py — Startup sequence and animated effects

import time
import sys
import os
import shutil

from rich.console import Console
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner

from ui.colors import C

ASCII_TITLE = r"""
  ███╗   ██╗███████╗██╗   ██╗██████╗  █████╗ ██╗     
  ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔══██╗██║     
  ██╔██╗ ██║█████╗  ██║   ██║██████╔╝███████║██║     
  ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██╔══██║██║     
  ██║ ╚████║███████╗╚██████╔╝██║  ██║██║  ██║███████╗
  ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
""".strip("\n")

SUBTITLE = "  Coding Intelligence  ·  v2.0  ·  Powered by ReAct"


def _term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _print_title(console: Console):
    lines = ASCII_TITLE.splitlines()
    total = len(lines)
    for i, line in enumerate(lines):
        frac = i / max(total - 1, 1)
        if frac < 0.6:
            color = C["cyan"]
        elif frac < 0.85:
            color = C["cyan_bright"]
        else:
            color = C["white"]
        t = Text(line, style=f"bold {color}")
        console.print(t)
        time.sleep(0.04)


def _print_subtitle(console: Console):
    _print_subtitle_text(console, SUBTITLE)


def _print_subtitle_text(console: Console, text: str):
    out = Text()
    for ch in text:
        out.append(ch, style=f"dim {C['gray']}")
        console.print(out, end="\r")
        time.sleep(0.012)
    console.print(out)


def _pulse_line(console: Console):
    width = min(_term_width() - 4, 72)
    frames = ["░", "▒", "▓", "█", "▓", "▒", "░", " "]
    steps = width + len(frames)
    start = time.time()
    duration = 0.6
    while time.time() - start < duration:
        elapsed = time.time() - start
        pos = int((elapsed / duration) * steps)
        row = []
        for x in range(width):
            fi = pos - x
            if 0 <= fi < len(frames):
                ch = frames[fi]
            else:
                ch = " "
            row.append(ch)
        line = "  " + "".join(row)
        t = Text(line, style=C["cyan_dim"])
        console.print(t, end="\r")
        time.sleep(0.018)
    console.print(" " * (width + 4), end="\r")


def run_startup_sequence(console: Console, mcp_init_fn, backend: str = ""):
    backend_label = backend or "ReAct"
    console.clear()
    console.print()
    _print_title(console)
    console.print()
    subtitle_text = f"  Code · Charts · Diagrams · Docs · Web Search  ·  {backend_label} backend"
    _print_subtitle_text(console, subtitle_text)
    console.print()
    _pulse_line(console)
    console.print()

    with Live(
        Spinner("dots", text=Text("  Initializing neural pathways...", style=C["cyan"])),
        console=console,
        refresh_per_second=15,
        transient=True,
    ):
        result = mcp_init_fn()

    if result:
        t = Text()
        t.append("  ✦  ", style=f"bold {C['green']}")
        t.append("Neural pathways active", style=C["green"])
        console.print(t)
    else:
        t = Text()
        t.append("  ✦  ", style=f"bold {C['amber']}")
        t.append("Neural pathways degraded — MCP unavailable", style=C["amber"])
        console.print(t)

    console.print()
    return result
