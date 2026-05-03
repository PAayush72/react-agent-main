# core/mcp_manager.py — Multi-server MCP connection manager
#
# Reads mcp_config.json and connects to all enabled MCP servers.
# Each server's tools are tracked so tool calls route to the correct server.

import os
import sys
import json
from typing import Dict, List, Any, Optional, Tuple

from rich.console import Console
from rich.theme import Theme
from fastmcp import Client

_theme = Theme({
    "success": "bold #10B981",
    "warning": "bold #FBBF24",
    "error": "bold #EF4444",
    "muted": "dim #9CA3AF",
    "accent2": "#A78BFA",
    "tool.name": "bold #22D3EE",
})

console = Console(theme=_theme)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_config.json")
BUILTIN_URL = "http://localhost:8000/mcp"


def load_mcp_config() -> Dict[str, Any]:
    """Load MCP server configuration from mcp_config.json."""
    if not os.path.exists(CONFIG_FILE):
        # No config file — return default built-in server
        return {
            "mcpServers": {
                "built-in": {
                    "url": BUILTIN_URL,
                    "enabled": True,
                }
            }
        }

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"  [warning]! mcp_config.json parse error: {e}[/]")
        console.print(f"  [muted]  Falling back to built-in server only[/]")
        return {"mcpServers": {"built-in": {"url": BUILTIN_URL, "enabled": True}}}

    # Ensure built-in server exists
    servers = config.get("mcpServers", {})
    if "built-in" not in servers:
        servers["built-in"] = {"url": BUILTIN_URL, "enabled": True}
        config["mcpServers"] = servers

    return config


class MCPManager:
    """Manages connections to multiple MCP servers and routes tool calls."""

    def __init__(self, silent: bool = False):
        self._clients: Dict[str, Client] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._tool_defs: List[Dict[str, Any]] = []
        self._connected: bool = False
        self._silent: bool = silent

    async def connect(self, silent: bool = False) -> None:
        """Connect to all enabled MCP servers from config."""
        if silent:
            self._silent = True
        config = load_mcp_config()
        servers = config.get("mcpServers", {})

        for name, server_cfg in servers.items():
            # Skip disabled servers and example entries
            if not server_cfg.get("enabled", True):
                continue
            if name.startswith("_"):
                continue

            try:
                client = self._create_client(name, server_cfg)
                await client.__aenter__()
                self._clients[name] = client

                # Discover tools from this server
                tools = await client.list_tools()
                tool_count = 0
                for t in tools:
                    tool_name = t.name
                    # Handle conflicts: first server wins, log warning
                    if tool_name in self._tool_to_server:
                        existing = self._tool_to_server[tool_name]
                        console.print(f"  [warning]! Tool '{tool_name}' from '{name}' conflicts with '{existing}' -- skipped[/]")
                        continue

                    self._tool_to_server[tool_name] = name
                    tool_count += 1

                    # Build tool definition
                    raw_schema = (
                        getattr(t, "inputSchema", None)
                        or getattr(t, "input_schema", None)
                        or getattr(t, "parameters", None)
                    )
                    if not raw_schema or not isinstance(raw_schema, dict):
                        raw_schema = {"type": "object", "properties": {}}

                    self._tool_defs.append({
                        "name": tool_name,
                        "description": getattr(t, "description", "") or "",
                        "input_schema": raw_schema,
                        "_server": name,
                    })

                desc = server_cfg.get("description", "")
                desc_suffix = f" -- {desc}" if desc else ""
                if not self._silent:
                    console.print(f"  [success]+ {name}[/] [muted]({tool_count} tools){desc_suffix}[/]")

            except Exception as e:
                if not self._silent:
                    console.print(f"  [error]x {name}[/] [muted]failed: {e}[/]")

        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect all clients."""
        for name, client in self._clients.items():
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        self._clients.clear()
        self._tool_to_server.clear()
        self._tool_defs.clear()
        self._connected = False

    def _create_client(self, name: str, cfg: Dict[str, Any]) -> Client:
        """Create a FastMCP Client from config entry."""
        if "url" in cfg:
            return Client(cfg["url"], timeout=15.0)
        elif "command" in cfg:
            # stdio transport — build the config dict that fastmcp expects
            server_config = {
                "mcpServers": {
                    name: {
                        "command": cfg["command"],
                        "args": cfg.get("args", []),
                    }
                }
            }
            if "env" in cfg:
                server_config["mcpServers"][name]["env"] = cfg["env"]
            return Client(server_config, timeout=15.0)
        else:
            raise ValueError(f"Server '{name}' must have 'url' or 'command' in config")

    # ── Public API ──

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return merged tool definitions from all servers."""
        return self._tool_defs

    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Which server owns this tool?"""
        return self._tool_to_server.get(tool_name)

    def get_client_for_tool(self, tool_name: str) -> Optional[Client]:
        """Get the MCP client that owns this tool."""
        server_name = self._tool_to_server.get(tool_name)
        if server_name:
            return self._clients.get(server_name)
        return None

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Route a tool call to the correct server."""
        client = self.get_client_for_tool(tool_name)
        if client is None:
            raise ValueError(f"No server found for tool '{tool_name}'")

        # For stdio multi-server clients, tool names are prefixed
        server_name = self._tool_to_server[tool_name]
        cfg = load_mcp_config().get("mcpServers", {}).get(server_name, {})

        # For both HTTP and stdio clients, call tools by their original name
        return await client.call_tool(tool_name, params)

    def get_server_summary(self) -> List[Tuple[str, int]]:
        """Return (server_name, tool_count) for display."""
        counts: Dict[str, int] = {}
        for tool_name, server_name in self._tool_to_server.items():
            counts[server_name] = counts.get(server_name, 0) + 1
        return list(counts.items())

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def total_tools(self) -> int:
        return len(self._tool_defs)

    @property
    def server_count(self) -> int:
        return len(self._clients)
