# ui/input_handler.py — prompt_toolkit styled input with history, completion, ESC ESC cancel

import os
import time
import threading
from typing import Optional, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import is_done

from ui.colors import C

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".neural_agent_history")

SLASH_COMMANDS = WordCompleter(
    [
        "/help", "/clear", "/compact", "/tokens", "/model",
        "/mcp", "/expand", "/history", "/quit", "/exit",
    ],
    sentence=True,
    ignore_case=True,
)

_PT_STYLE = PTStyle.from_dict({
    "prompt":                              f"bold fg:{C['cyan']}",
    "completion-menu.completion":          "bg:#1a1a2e fg:#aaaaaa",
    "completion-menu.completion.current":  f"bg:#00CED1 fg:#000000 bold",
    "scrollbar.background":                "bg:#3a3a3a",
    "scrollbar.button":                    f"bg:{C['cyan']}",
    "auto-suggestion":                     f"fg:{C['gray']}",
})

_PROMPT_MAIN   = ANSI(f"\033[1;38;2;0;206;209m❯ \033[0m")
_PROMPT_MCP    = ANSI(f"\033[1;38;2;255;175;0mmcp ❯ \033[0m")
_PROMPT_MODEL  = ANSI(f"\033[1;38;2;175;135;255mmodel ❯ \033[0m")
_PROMPT_PLAIN  = lambda label: ANSI(f"\033[1;38;2;0;206;209m{label} ❯ \033[0m")


class InputHandler:
    def __init__(self):
        self._session:     Optional[PromptSession] = None
        self._sub_session: Optional[PromptSession] = None

        # ESC ESC detection
        self._esc_time:     float    = 0.0
        self._cancel_cb:    Optional[Callable] = None
        self._esc_window    = 0.5    # seconds between two ESC presses

    def set_cancel_callback(self, cb: Callable):
        self._cancel_cb = cb

    def _get_session(self) -> PromptSession:
        if self._session is None:
            kb = KeyBindings()

            @kb.add("escape", eager=True)
            def _on_esc(event):
                now = time.time()
                if now - self._esc_time < self._esc_window:
                    # Double ESC
                    if self._cancel_cb:
                        self._cancel_cb()
                    self._esc_time = 0.0
                else:
                    self._esc_time = now

            self._session = PromptSession(
                history=FileHistory(HISTORY_FILE),
                auto_suggest=AutoSuggestFromHistory(),
                completer=SLASH_COMMANDS,
                style=_PT_STYLE,
                complete_while_typing=True,
                key_bindings=kb,
            )
        return self._session

    def _get_sub_session(self) -> PromptSession:
        if self._sub_session is None:
            self._sub_session = PromptSession(style=_PT_STYLE)
        return self._sub_session

    def prompt(self) -> Optional[str]:
        try:
            raw = self._get_session().prompt(_PROMPT_MAIN)
            return raw.strip() if raw else ""
        except EOFError:
            return None
        except KeyboardInterrupt:
            return ""

    def prompt_sub(self, prefix: str) -> Optional[str]:
        """Prompt inside a submenu with a custom prefix."""
        p = _PROMPT_PLAIN(prefix)
        try:
            raw = self._get_sub_session().prompt(p)
            return raw.strip() if raw else ""
        except (EOFError, KeyboardInterrupt):
            return None

    async def prompt_sub_async(self, prefix: str) -> Optional[str]:
        """Async version of prompt_sub — use when inside a running event loop."""
        p = _PROMPT_PLAIN(prefix)
        try:
            raw = await self._get_sub_session().prompt_async(p)
            return raw.strip() if raw else ""
        except (EOFError, KeyboardInterrupt):
            return None

    def prompt_plain(self, label: str) -> Optional[str]:
        """Simple one-shot prompt (no history/completion) for value entry."""
        p = ANSI(f"\033[1;38;2;200;200;200m{label}\033[0m")
        try:
            raw = PromptSession(style=_PT_STYLE).prompt(p)
            return raw.strip() if raw else ""
        except (EOFError, KeyboardInterrupt):
            return None

    async def prompt_plain_async(self, label: str) -> Optional[str]:
        """Async version of prompt_plain — use when inside a running event loop."""
        p = ANSI(f"\033[1;38;2;200;200;200m{label}\033[0m")
        try:
            raw = await PromptSession(style=_PT_STYLE).prompt_async(p)
            return raw.strip() if raw else ""
        except (EOFError, KeyboardInterrupt):
            return None
