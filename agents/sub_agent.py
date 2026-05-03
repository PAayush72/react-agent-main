# agents/sub_agent.py — Sub-agent delegation system
#
# STATUS: NOT YET WIRED IN — this module is implemented but not called from
# core/agent.py or main.py. It is preserved for future integration.
# See Flow.md "Known Issues / TODOs" for the planned use case.

import os
import sys

# Fix Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel

console = Console()


@dataclass
class SubAgentConfig:
    max_steps: int = 40
    max_depth: int = 2
    temperature: float = 0.2


class SubAgentSpawner:
    """Spawns focused sub-agents with restricted tool access and fresh context."""

    _DEFAULT_TOOLS: Dict[str, List[str]] = {
        "researcher": ["list_files", "read_file", "web_search", "fetch_page", "grep_search", "glob_search"],
        "coder": ["list_files", "read_file", "write_file", "patch_file", "bash"],
        "reviewer": ["list_files", "read_file", "grep_search", "glob_search", "bash"],
    }

    def __init__(self, parent_agent, config: Optional[SubAgentConfig] = None):
        self.parent = parent_agent
        self.config = config or SubAgentConfig()

    async def spawn(
        self,
        task: str,
        role: str = "coder",
        allowed_tools: Optional[List[str]] = None,
        context: str = "",
    ) -> str:
        if self.config.max_depth <= 0:
            return "Error: Maximum sub-agent depth reached."

        tools = allowed_tools or self._DEFAULT_TOOLS.get(role, ["list_files", "read_file"])

        console.print()
        console.print(Panel(
            f"[bold]Role:[/] {role}\n[bold]Tools:[/] {', '.join(tools)}\n[bold]Task:[/] {task[:120]}{'...' if len(task) > 120 else ''}",
            title="[bold magenta]>> Spawning Sub-Agent[/]",
            border_style="magenta",
        ))

        sub = _SubAgentInstance(
            mcp_url="http://localhost:8000/mcp",
            allowed_tools=tools,
            max_steps=self.config.max_steps,
            temperature=self.config.temperature,
        )

        prompt = self._build_prompt(task, context)
        result = await sub.run(prompt)

        console.print(Panel(
            result[:600] + ("..." if len(result) > 600 else ""),
            title="[bold green]+ Sub-Agent Result[/]",
            border_style="green",
        ))

        return result

    def _build_prompt(self, task: str, context: str) -> str:
        lines = [
            "You are a focused sub-agent. Complete this specific task.",
            "",
            f"TASK: {task}",
        ]
        if context:
            lines.extend(["", f"CONTEXT: {context}"])
        lines.extend([
            "",
            "Rules:",
            "- Focus only on this task.",
            "- Do not ask clarifying questions.",
            "- Return a clear, concise result when done.",
            "- If you cannot complete the task, explain why.",
        ])
        return "\n".join(lines)


class _SubAgentInstance:
    """A lightweight agent instance with its own context and restricted tools."""

    def __init__(self, mcp_url: str, allowed_tools: List[str], max_steps: int, temperature: float):
        from fastmcp import Client
        self.mcp = Client(mcp_url)
        self.allowed_tools = set(allowed_tools)
        self.max_steps = max_steps
        self.temperature = temperature
        self.messages: List[Dict[str, Any]] = []
        self.step_count = 0

    async def run(self, prompt: str) -> str:
        async with self.mcp:
            return await self._loop(prompt)

    async def _loop(self, user_message: str) -> str:
        from llm_model import call_model, call_model_stream, ToolCall, LLMResponse
        import json as _json

        self.messages.append({"role": "user", "content": user_message})

        all_tools = await self._get_tool_definitions()
        tool_defs = [t for t in all_tools if t["name"] in self.allowed_tools]

        recent_tool_calls = []
        loop_threshold = 3

        for step_i in range(self.max_steps):
            self.step_count += 1

            console.print(f"\n[dim]  [Sub-Agent Step {step_i + 1}/{self.max_steps}][/dim]")
            status = console.status("[bold cyan]  Sub-agent thinking...", spinner="dots")
            status.start()

            response = LLMResponse()
            current_tool = None
            tool_input = ""
            thinking = True

            try:
                for chunk in call_model_stream(self.messages, tool_defs):
                    if chunk.type == "text":
                        if thinking:
                            status.stop()
                            thinking = False
                        response.content += chunk.content
                        console.print(f"  [dim]{chunk.content}[/dim]", end="")
                        console.file.flush()
                    elif chunk.type == "tool_start":
                        current_tool = {"id": chunk.tool_id, "name": chunk.tool_name, "input": ""}
                        tool_input = ""
                    elif chunk.type == "tool_end":
                        if chunk.tool_input and isinstance(chunk.tool_input, dict):
                            params = chunk.tool_input
                        else:
                            try:
                                params = _json.loads(tool_input) if tool_input else {}
                            except Exception:
                                params = {}
                        response.tool_calls.append(ToolCall(
                            id=chunk.tool_id,
                            name=chunk.tool_name,
                            parameters=params,
                        ))
                    elif chunk.type == "done":
                        response.stop_reason = chunk.stop_reason
                        response.input_tokens = chunk.input_tokens
                        response.output_tokens = chunk.output_tokens

                if thinking:
                    status.stop()
                console.print()
            except Exception as e:
                status.stop()
                return f"Sub-agent LLM error: {e}"

            if not response.tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [],
                })
                return response.content or "(Sub-agent produced no output)"

            for tc in response.tool_calls:
                call_sig = (tc.name, _json.dumps(tc.parameters or {}, sort_keys=True))
                recent_tool_calls.append(call_sig)
            if len(recent_tool_calls) > loop_threshold * 2:
                recent_tool_calls = recent_tool_calls[-(loop_threshold * 2):]

            if len(recent_tool_calls) >= loop_threshold:
                last_n = recent_tool_calls[-loop_threshold:]
                if len(set(last_n)) == 1:
                    console.print(f"\n[bold red]! Sub-agent loop detected: repeated '{last_n[0][0]}' {loop_threshold}x. Breaking.[/]")
                    return response.content or f"Sub-agent got stuck in a loop repeating '{last_n[0][0]}'."

            self.messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls,
            })

            tool_results = []
            for tc in response.tool_calls:
                if tc.name not in self.allowed_tools:
                    result = f"Tool '{tc.name}' is not available for this sub-agent."
                else:
                    result = await self._execute(tc)
                tool_results.append({"tool_use_id": tc.id, "content": result})

            self.messages.append({"role": "tool_result", "results": tool_results})

        return f"Sub-agent reached max steps ({self.max_steps}). Last output: {response.content}"

    async def _get_tool_definitions(self):
        tools = await self.mcp.list_tools()
        formatted = []
        for t in tools:
            raw_schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None) or getattr(t, "parameters", None)
            if not raw_schema or not isinstance(raw_schema, dict):
                raw_schema = {"type": "object", "properties": {}}
            formatted.append({
                "name": t.name,
                "description": getattr(t, "description", "") or "",
                "input_schema": raw_schema,
            })
        return formatted

    async def _execute(self, tool_call) -> str:
        import json

        params = dict(tool_call.parameters or {})

        aliases = {
            "write_file": {"file_path": "path", "file": "path"},
            "read_file": {"file_path": "path", "file": "path"},
            "patch_file": {"file_path": "path", "file": "path", "old": "search", "new": "replace"},
            "bash": {"cmd": "command", "code": "command"},
            "web_search": {"search_query": "query", "q": "query"},
            "fetch_page": {"page_url": "url", "link": "url"},
        }
        for old, new in aliases.get(tool_call.name, {}).items():
            if old in params and new not in params:
                params[new] = params.pop(old)

        if not params and tool_call.name in ("bash", "write_file", "patch_file", "read_file"):
            return f"Error: '{tool_call.name}' called with no parameters. Provide the required arguments."

        console.print(f"  [dim]  >> {tool_call.name}({json.dumps(params, indent=4)})[/dim]")

        try:
            raw = await self.mcp.call_tool(tool_call.name, params)
            result = self._extract(raw)
            console.print(f"  [dim]  <- {result[:200]}{'...' if len(result) > 200 else ''}[/dim]")
            return result
        except Exception as e:
            return f"Tool error: {e}"

    def _extract(self, raw) -> str:
        import json

        if hasattr(raw, "content"):
            texts = []
            for item in raw.content:
                texts.append(item.text if hasattr(item, "text") else str(item))
            return "\n".join(texts) if texts else str(raw)
        if hasattr(raw, "data"):
            return str(raw.data)
        if isinstance(raw, dict):
            if "content" in raw:
                return json.dumps(raw["content"], indent=2) if not isinstance(raw["content"], str) else raw["content"]
            if "result" in raw:
                return str(raw["result"])
            return json.dumps(raw, indent=2)
        return str(raw)
