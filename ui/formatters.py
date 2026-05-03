# ui/formatters.py — Code, JSON, diff, text formatters + session log

import json
import re
import os
from datetime import datetime
from typing import Optional, List

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text
from rich.panel import Panel

from ui.colors import C

_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".html": "html", ".css": "css",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".md": "markdown", ".rs": "rust", ".go": "go",
    ".cpp": "cpp", ".c": "c", ".h": "c", ".java": "java",
    ".rb": "ruby", ".php": "php", ".sql": "sql", ".toml": "toml",
    ".xml": "xml",
}

MAX_CODE_LINES = 6
MAX_TEXT_LINES = 8


def detect_language(path: str, content: str = "") -> str:
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
    return (s.startswith("{") and s.endswith("}")) or \
           (s.startswith("[") and s.endswith("]"))


def _collapse_json(obj, depth: int = 0, max_depth: int = 2) -> str:
    if depth >= max_depth:
        if isinstance(obj, dict):
            return f"{{ {len(obj)} keys... }}"
        if isinstance(obj, list):
            return f"[ {len(obj)} items... ]"
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        parts = []
        for k, v in list(obj.items())[:8]:
            parts.append(f'  {"  " * depth}"{k}": {_collapse_json(v, depth+1, max_depth)}')
        inner = ",\n".join(parts)
        indent = "  " * depth
        return "{\n" + inner + f"\n{indent}}}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if depth >= max_depth - 1:
            return f"[ {len(obj)} items... ]"
        parts = [f'  {"  " * depth}{_collapse_json(v, depth+1, max_depth)}' for v in obj[:6]]
        if len(obj) > 6:
            parts.append(f'  {"  " * depth}... ({len(obj) - 6} more)')
        indent = "  " * depth
        return "[\n" + ",\n".join(parts) + f"\n{indent}]"
    return json.dumps(obj)


def format_json_result(text: str, console: Console, step: int = 0) -> bool:
    try:
        obj = json.loads(text.strip())
        collapsed = _collapse_json(obj)
        syn = Syntax(
            collapsed, "json",
            theme="monokai",
            background_color="default",
            line_numbers=False,
            word_wrap=False,
        )
        step_tag = _step_prefix(step)
        console.print(f"{step_tag}┌─ result {'─' * 20}┐", style=f"dim {C['gray']}")
        console.print(syn)
        console.print(f"{step_tag}└{'─' * 28}┘", style=f"dim {C['gray']}")
        return True
    except Exception:
        return False


def format_code_result(text: str, console: Console,
                       filename: str = "", step: int = 0) -> bool:
    lines = text.splitlines()
    if len(lines) < 3:
        return False

    lang = detect_language(filename, text) if filename else "text"
    if lang == "text":
        for kw in ("def ", "class ", "import ", "function ", "const ", "let ", "var "):
            if any(kw in l for l in lines[:10]):
                lang = "python" if "def " in text or "import " in text else "javascript"
                break

    total = len(lines)
    shown = lines[:MAX_CODE_LINES]
    hidden = total - MAX_CODE_LINES

    display = "\n".join(shown)
    if hidden > 0:
        display += f"\n... [+{hidden} lines hidden]"

    step_tag = _step_prefix(step)
    title_right = f"{total} lines"
    title_left = filename or lang
    width = 52
    pad = width - len(title_left) - len(title_right) - 6
    header = f"{step_tag}┌─ {title_left} {'─' * max(pad, 2)} {title_right} ─┐"
    console.print(header, style=f"dim {C['gray']}")

    syn = Syntax(
        display, lang,
        theme="monokai",
        background_color="default",
        line_numbers=True,
        word_wrap=False,
    )
    console.print(syn)
    console.print(f"{step_tag}└{'─' * (width + 2)}┘", style=f"dim {C['gray']}")
    return True


def format_plain_result(text: str, console: Console, step: int = 0):
    lines = text.splitlines()
    total = len(lines)
    shown = lines[:MAX_TEXT_LINES]

    step_tag = _step_prefix(step)
    for line in shown:
        t = Text()
        t.append(f"{step_tag}╎  ", style=f"dim {C['gray']}")
        t.append(line, style=f"dim {C['white_dim']}")
        console.print(t)

    if total > MAX_TEXT_LINES:
        t = Text()
        t.append(f"{step_tag}╎  ", style=f"dim {C['gray']}")
        t.append(f"[+{total - MAX_TEXT_LINES} more lines]", style=f"dim {C['gray']}")
        console.print(t)


def format_diff(diff_text: str, console: Console):
    lines = diff_text.splitlines()
    out = Text()
    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line + "\n", style=f"bold {C['green']}")
        elif line.startswith("-") and not line.startswith("---"):
            out.append(line + "\n", style=f"bold {C['red']}")
        elif line.startswith("@@"):
            out.append(line + "\n", style=f"bold {C['cyan']}")
        elif line.startswith("---") or line.startswith("+++"):
            out.append(line + "\n", style=f"dim {C['gray']}")
        else:
            out.append(line + "\n", style=f"dim {C['white_dim']}")
    console.print(Panel(out, border_style=C["gray_dark"],
                        title=f"[dim {C['gray']}]diff[/]", padding=(0, 1)))


def _step_prefix(step: int) -> str:
    if step <= 0:
        return ""
    return f"[dim {C['gray']}][{step}][/] "


def auto_format_result(text: str, console: Console,
                       tool_name: str = "", step: int = 0):
    if not text or not text.strip():
        return

    text = text.strip()

    # Try JSON first
    if _looks_like_json(text):
        if format_json_result(text, console, step):
            return

    # Detect filename from read_file result header: "path/to/file.py (N lines)"
    filename = ""
    first_line = text.splitlines()[0] if text.splitlines() else ""
    m = re.match(r"^(.+\.\w+)\s+\(\d+", first_line)
    if m:
        filename = m.group(1).strip()

    # Diff results
    if text.startswith("---") or ("--- diff ---" in text):
        diff_part = text
        if "--- diff ---" in text:
            diff_part = text.split("--- diff ---", 1)[1]
        format_diff(diff_part, console)
        return

    # Code-like results
    lines = text.splitlines()
    if len(lines) >= 3:
        if format_code_result(text, console, filename, step):
            return

    # Plain text
    format_plain_result(text, console, step)


# ───────────────── SESSION LOG FORMATTER ───────────────── #

def format_session_log(
    model: str,
    backend: str,
    session_start: datetime,
    steps: List[dict],
    messages: List[dict],
    files_created: List[str],
    files_modified: List[str],
    total_tokens: int,
    total_calls: int,
) -> str:
    now    = datetime.now()
    delta  = now - session_start
    m, s   = divmod(int(delta.total_seconds()), 60)
    dur    = f"{m:02d}:{m:02d}" if m else f"00:{s:02d}"

    lines = [
        "# Neural Terminal Session",
        f"Date: {session_start.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Model: {model}",
        f"Backend: {backend}",
        f"Duration: {m:02d}:{s:02d}",
        f"Total tokens: {total_tokens:,}",
        f"Tool calls: {total_calls}",
        "",
        "## Conversation",
        "",
    ]

    # Rebuild conversation from messages
    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role == "user":
            content = msg.get("content", "")
            if content and not content.startswith("STOP trying"):
                lines.append(f"**You:** {content}")
                lines.append("")
        elif role == "assistant":
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            if content:
                lines.append(f"**Agent:** {content}")
            for tc in tool_calls:
                name   = tc.name if hasattr(tc, "name") else tc.get("name", "")
                params = tc.parameters if hasattr(tc, "parameters") else tc.get("parameters", {})
                key    = next(iter(params.values()), "") if params else ""
                key_s  = str(key)[:40] if key else ""
                lines.append(f"[action] {name}({key_s!r})")
            lines.append("")
        elif role == "tool_result":
            for tr in msg.get("results", []):
                content = str(tr.get("content", ""))[:200]
                lines.append(f"[observe] {content}")
            lines.append("")

    lines += [
        "## Files Modified",
        *([f"- {f}" for f in files_modified] or ["- (none)"]),
        "",
        "## Files Created",
        *([f"- {f}" for f in files_created] or ["- (none)"]),
        "",
    ]

    return "\n".join(lines)


def save_session_log(
    cwd: str,
    model: str,
    backend: str,
    session_start: datetime,
    steps: List[dict],
    messages: List[dict],
    files_created: List[str],
    files_modified: List[str],
    total_tokens: int,
    total_calls: int,
) -> Optional[str]:
    try:
        saves_dir = os.path.join(cwd, "saves", "sessions")
        os.makedirs(saves_dir, exist_ok=True)
        ts       = session_start.strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(saves_dir, f"session_{ts}.md")
        content  = format_session_log(
            model, backend, session_start, steps, messages,
            files_created, files_modified, total_tokens, total_calls,
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return os.path.relpath(filepath, cwd)
    except Exception:
        return None

