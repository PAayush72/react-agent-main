# core/agent.py — ReAct Agent with MCP tool calling

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import json
import time
from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from core.mcp_manager import MCPManager
from llm_model import call_model_stream, ToolCall, LLMResponse
from ui import neural_ui as ui


@dataclass
class AgentConfig:
    max_steps:   int   = 50
    temperature: float = 0.2


WRITE_TOOLS = {"write_file", "patch_file", "delete_file", "bash"}

SYSTEM_PROMPT = """\
You are a powerful AI assistant operating inside a terminal-based ReAct loop.
You can help with coding, data analysis, charts, diagrams, documents, web search, news retrieval, and more.

## Capabilities

### 1. Coding & Files
- Read, write, patch, delete files in any language
- Run bash commands, install packages, execute scripts
- Create and modify Jupyter notebooks

### 2. Charts & Visualizations
- generate_plotly_chart(data, chart_type, title) — bar, line, pie, scatter, histogram, heatmap
- smart_chart(user_query, data) — describe what you want, it figures out the best chart type
- search_and_chart(query, chart_type) — search the web for data, then chart it automatically

### 3. Diagrams & Flow Charts
- generate_flow_diagram(spec) — create flowcharts, architecture diagrams, sequence diagrams
  Spec format: "A -> B -> C; A -> D" or describe it in plain English

### 4. Documents & Reports
- write_file(path, content) — write markdown reports, READMEs, docs
- For structured reports: create .md files with headings, tables, code blocks

### 5. Web Search & News
- web_search(query, max_results) — search the web for current information, news, docs
- fetch_page(url) — fetch and read any web page
- search_and_chart(query) — search + visualize data in one step

### 6. Jupyter Notebooks
- generate_notebook(path, cells) — create a complete .ipynb notebook
- modify_notebook_cells(path, ...) — edit existing notebook cells

## How You Work
THINK → USE TOOL → OBSERVE → REPEAT until the task is complete.
When finished, respond with plain text (no tool call).

## Rules
1. Always read files before writing. Never guess file contents.
2. Be precise and minimal. Prefer patch_file over write_file for edits.
3. Never fabricate tool results. If a tool fails, report and adjust.
4. For large files use bash with python3 -c "..." to write inline.
5. Never split a large file across multiple write_file calls.
6. For charts: always save output to saves/charts/ and tell the user the path.
7. For web search: cite sources. If results are stale, say so.
8. For diagrams: save to saves/charts/ as .png or .html and show the path.
9. For documents: save to saves/docs/ unless user specifies otherwise.

## Smart File Placement
- Python project files → project root or src/, lib/, tests/
- Test files → tests/
- Documentation → docs/ or README in project root
- Charts/plots → saves/charts/
- Reports/docs → saves/docs/
- Utility scripts → saves/scripts/
- Data files (.json, .csv) → data/
- Config files → project root
Always create the target directory if it does not exist.
Always tell the user exactly where each file is saved.

## Tool Usage Tips
- patch_file(path, search, replace) — surgical single-occurrence edit
- bash(command) — simple commands and python3 -c inline scripts
- write_file(path, content) — always include the content parameter
- grep_search(pattern, path) — search text in files
- glob_search(pattern) — find files by name pattern
- web_search(query) — get current news, docs, data from the web
- fetch_page(url) — read any URL
- generate_plotly_chart(data, chart_type, title) — create interactive charts
- smart_chart(user_query, data) — AI-driven chart generation
- generate_flow_diagram(spec) — flowcharts and diagrams
- generate_notebook(path, cells) — create Jupyter notebooks
"""


class Agent:
    def __init__(self):
        self.config              = AgentConfig()
        self.messages: List[Dict[str, Any]] = []
        self.step_count          = 0
        self.total_input_tokens  = 0
        self.total_output_tokens = 0
        self._model              = "auto"

    async def chat(self, user_message: str) -> str:
        if not self.messages:
            self.messages.append({"role": "system", "content": SYSTEM_PROMPT})

        manager = MCPManager()
        try:
            await manager.connect(silent=True)
            result = await self._chat_loop(user_message, manager)
        finally:
            await manager.disconnect()
        return result

    # ── Streaming ── #

    def _call_with_streaming(self, messages, tool_defs, step: int = 0):
        response     = LLMResponse()
        current_tool = None
        tool_input   = ""
        model_used   = ""
        start_time   = time.time()
        first_token  = True
        thought_open = False

        ui.start_thinking("thinking")

        for chunk in call_model_stream(messages, tool_defs):

            if chunk.type == "status":
                ui.update_thinking(chunk.content)

            elif chunk.type == "text":
                if first_token:
                    ui.stop_thinking()
                    first_token = False
                response.content += chunk.content
                from ui import console as _c
                if not thought_open:
                    _c.print()
                    _c.print(f"  [dim {ui._thought_block._step and f'[{step}] ' or ''}]", end="")
                    thought_open = True
                _c.print(chunk.content, end="", highlight=False)
                _c.file.flush()

            elif chunk.type == "tool_start":
                if thought_open:
                    from ui import console as _c
                    _c.print()
                    thought_open = False
                ui.stop_thinking()
                first_token  = False
                current_tool = {"id": chunk.tool_id, "name": chunk.tool_name}
                tool_input   = ""

            elif chunk.type == "tool_delta":
                tool_input += chunk.content

            elif chunk.type == "tool_end":
                if chunk.tool_input and isinstance(chunk.tool_input, dict):
                    params = chunk.tool_input
                else:
                    try:
                        params = json.loads(tool_input) if tool_input else {}
                    except Exception:
                        params = {}
                response.tool_calls.append(ToolCall(
                    id=chunk.tool_id,
                    name=chunk.tool_name,
                    parameters=params,
                ))
                current_tool = None
                tool_input   = ""

            elif chunk.type == "done":
                response.stop_reason   = chunk.stop_reason
                response.input_tokens  = chunk.input_tokens
                response.output_tokens = chunk.output_tokens
                model_used             = chunk.model_used

        ui.stop_thinking()
        if thought_open:
            from ui import console as _c
            _c.print()

        elapsed = time.time() - start_time
        ui.print_tokens(response.input_tokens, response.output_tokens, elapsed, model_used)

        self.total_input_tokens  += response.input_tokens
        self.total_output_tokens += response.output_tokens
        ui.update_status(tokens=response.input_tokens + response.output_tokens, calls=1)

        return response

    # ── ReAct loop ── #

    async def _chat_loop(self, user_message: str, manager: MCPManager) -> str:
        self.messages.append({"role": "user", "content": user_message})

        tool_defs             = manager.get_tool_definitions()
        recent_tool_calls     = []
        loop_threshold        = 3
        failed_write_attempts = 0
        task_start            = time.time()
        total_tool_calls      = 0

        for step in range(self.config.max_steps):
            self.step_count += 1
            react_step       = step + 1

            if step > 0:
                ui.print_step_indicator(react_step, self.config.max_steps)

            try:
                response = self._call_with_streaming(self.messages, tool_defs, step=react_step)
            except Exception as e:
                ui.stop_thinking()
                ui.print_error(str(e))
                return f"LLM error: {e}"

            # No tool calls → final answer
            if not response.tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [],
                })
                return response.content

            # ── Loop detection ──
            for tc in response.tool_calls:
                call_sig = (tc.name, json.dumps(tc.parameters or {}, sort_keys=True))
                recent_tool_calls.append(call_sig)
            if len(recent_tool_calls) > loop_threshold * 2:
                recent_tool_calls = recent_tool_calls[-(loop_threshold * 2):]

            if len(recent_tool_calls) >= loop_threshold:
                last_n = recent_tool_calls[-loop_threshold:]
                if len(set(last_n)) == 1:
                    tool_name = last_n[0][0]
                    ui.print_loop_error(f"Loop detected: '{tool_name}' repeated {loop_threshold}x")
                    return response.content or f"Stuck repeating '{tool_name}'."

            if len(recent_tool_calls) >= 4:
                last4 = [c[0] for c in recent_tool_calls[-4:]]
                if all(n in {"write_file", "bash"} for n in last4) and len(set(last4)) > 1:
                    ui.print_loop_error("Loop detected: alternating write_file/bash failures")
                    return response.content or "Stuck in write_file/bash loop."

            # ── write_file without content recovery ──
            for tc in response.tool_calls:
                if tc.name == "write_file" and "content" not in (tc.parameters or {}):
                    failed_write_attempts += 1

            if failed_write_attempts >= 2:
                failed_write_attempts = 0
                ui.print_warning("write_file called without content — switching to bash")
                self.messages.append({
                    "role": "user",
                    "content": (
                        "STOP trying write_file. The file is too large for tool parameters. "
                        "Use bash with python3 -c to write the file inline. "
                        "Do NOT call write_file again."
                    ),
                })
                continue

            self.messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls,
            })

            # ── Execute tool calls ──
            tool_results = []
            for tool_call in response.tool_calls:
                total_tool_calls += 1
                result = await self._execute_tool_call(tool_call, manager, step=react_step)
                tool_results.append({
                    "tool_use_id": tool_call.id,
                    "content":     result,
                })

            self.messages.append({
                "role":    "tool_result",
                "results": tool_results,
            })

        ui.print_warning("Max steps reached")
        return "Max steps reached."

    # ── Param normalization ── #

    _PARAM_ALIASES = {
        "write_file":  {"file_path": "path", "file": "path", "filepath": "path", "filename": "path"},
        "read_file":   {"file_path": "path", "file": "path", "filepath": "path", "filename": "path"},
        "patch_file":  {"file_path": "path", "file": "path", "filepath": "path",
                        "old": "search", "new": "replace", "replacement": "replace"},
        "delete_file": {"file_path": "path", "file": "path", "filepath": "path", "filename": "path"},
        "revert_file": {"file_path": "path", "file": "path", "filepath": "path"},
        "bash":        {"cmd": "command", "code": "command", "script": "command", "cmd_line": "command"},
        "web_search":  {"query": "query", "search_query": "query", "q": "query"},
        "fetch_page":  {"page_url": "url", "link": "url", "uri": "url"},
        "grep_search": {"query": "pattern", "search": "pattern", "text": "pattern", "regex": "pattern"},
        "glob_search": {"glob": "pattern", "path": "pattern", "query": "pattern"},
        "generate_plotly_chart": {"chart_data": "data", "type": "chart_type", "chart_title": "title"},
        "smart_chart": {"query": "user_query", "chart_data": "data", "chart_colors": "colors"},
        "generate_flow_diagram": {"diagram": "spec", "edges": "spec", "flow_spec": "spec"},
        "search_and_chart": {"q": "query", "search_query": "query", "type": "chart_type"},
    }

    _REQUIRED_PARAMS = {
        "write_file":  ["path", "content"],
        "read_file":   ["path"],
        "patch_file":  ["path", "search", "replace"],
        "delete_file": ["path"],
        "revert_file": ["path"],
        "bash":        ["command"],
        "grep_search": ["pattern"],
        "glob_search": ["pattern"],
        "generate_plotly_chart": ["data"],
        "smart_chart": ["user_query", "data"],
        "generate_flow_diagram": ["spec"],
        "web_search":  ["query"],
        "fetch_page":  ["url"],
        "search_and_chart": ["query"],
    }

    # ── Tool execution ── #

    async def _execute_tool_call(self, tool_call, manager: MCPManager,
                                 step: int = 0) -> str:
        tool_name = tool_call.name
        params    = dict(tool_call.parameters or {})

        for old, new in self._PARAM_ALIASES.get(tool_name, {}).items():
            if old in params and new not in params:
                params[new] = params.pop(old)

        missing = [p for p in self._REQUIRED_PARAMS.get(tool_name, []) if p not in params]
        if missing:
            msg = f"Missing required parameters for '{tool_name}': {', '.join(missing)}"
            ui.print_error(msg)
            return msg

        ui.print_action(tool_name, params, step=step)

        if tool_name in WRITE_TOOLS:
            if not ui.print_permission_prompt(tool_name, params):
                ui.print_warning("Denied")
                return "Tool execution denied by user."

        if tool_name == "write_file" and "content" not in params:
            return "BLOCKED: write_file requires 'content' parameter."

        if not params and tool_name in ("bash", "write_file", "patch_file", "read_file"):
            return f"Error: '{tool_name}' called with no parameters."

        try:
            raw        = await manager.call_tool(tool_name, params)
            result_str = self._extract_mcp_result(raw)

            if result_str and len(result_str.strip()) > 5:
                ui.print_observation(result_str, step=step, tool_name=tool_name)

            return result_str

        except Exception as e:
            err = f"Tool execution error: {e}"
            ui.print_error(err)
            return err

    def _extract_mcp_result(self, raw) -> str:
        if hasattr(raw, "content"):
            texts = []
            for item in raw.content:
                texts.append(item.text if hasattr(item, "text") else str(item))
            return "\n".join(texts) if texts else str(raw)
        if hasattr(raw, "data"):
            return str(raw.data)
        if isinstance(raw, dict):
            if "content" in raw:
                return self._format_result(raw["content"])
            if "result" in raw:
                return str(raw["result"])
            return json.dumps(raw, indent=2)
        return self._format_result(raw)

    def _format_result(self, result) -> str:
        if isinstance(result, str):  return result
        if isinstance(result, dict): return json.dumps(result, indent=2)
        if isinstance(result, list): return "\n".join(str(x) for x in result)
        return str(result)

    # ── Session commands ── #

    def clear(self):
        self.messages            = []
        self.step_count          = 0
        self.total_input_tokens  = 0
        self.total_output_tokens = 0

    def compact(self):
        from context.compression import ContextCompressor
        if len(self.messages) <= 4:
            ui.print_info("Nothing to compact")
            return
        compressor = ContextCompressor()
        old_tokens = compressor._count_tokens(self.messages)
        self.messages = compressor.compress(self.messages, target_tokens=30000)
        new_tokens    = compressor._count_tokens(self.messages)
        saved_pct     = int((1 - new_tokens / max(old_tokens, 1)) * 100)
        if new_tokens < old_tokens:
            ui.print_info(
                f"✦  Compressed: {old_tokens:,} → {new_tokens:,} tokens  (saved {saved_pct}%)"
            )
        else:
            ui.print_info("Context already within limits")

    def set_model(self, model: str):
        from llm_model import set_active_backend
        set_active_backend(model)
        self._model = model

    def get_token_stats(self) -> dict:
        return {
            "steps":         self.step_count,
            "messages":      len(self.messages),
            "input_tokens":  self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens":  self.total_input_tokens + self.total_output_tokens,
        }
