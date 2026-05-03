# tools/registry.py — Tool registry with proper schemas for Bedrock converse API
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


class ToolRegistry:
    """Registry for managing tools and their definitions"""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._definitions: List[ToolDefinition] = []
        self._permissions: Dict[str, str] = {}  # tool_name -> permission level

    def register(self, name: str, func: Callable, description: str = "",
                 input_schema: Optional[Dict[str, Any]] = None,
                 permission_level: str = "none"):
        """Register a tool with the registry"""
        self._tools[name] = func
        if input_schema is None:
            input_schema = {"type": "object", "properties": {}}

        definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema
        )
        self._definitions.append(definition)
        self._permissions[name] = permission_level

    def get(self, name: str) -> Optional[Callable]:
        """Get a tool function by name"""
        return self._tools.get(name)

    def get_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions in the format expected by LLMs"""
        return [
            {
                "name": d.name,
                "description": d.description,
                "input_schema": d.input_schema
            }
            for d in self._definitions
        ]

    def get_permission_level(self, tool_name: str) -> str:
        """Get permission level for a tool"""
        return self._permissions.get(tool_name, "none")


# ── Global Registry ──────────────────────────────────────────────

TOOL_REGISTRY = ToolRegistry()

# Import tool functions
from tools.file_tools import list_files, read_file, write_file, patch_file
from tools.bash_tools import execute_bash
from tools.search_tools import glob_search, grep_search

# Try importing web tools (may fail if requests/bs4 not installed)
try:
    from tools.web_tools import web_search, fetch_page
    _has_web_tools = True
except ImportError:
    _has_web_tools = False


# ── Register Tools ───────────────────────────────────────────────

TOOL_REGISTRY.register(
    "list_files",
    list_files,
    "List files and directories at the given path. Returns file names with sizes.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: current directory)"
            }
        },
        "required": ["path"]
    },
    "none"
)

TOOL_REGISTRY.register(
    "read_file",
    read_file,
    "Read the contents of a file with line numbers. Can specify a line range to read a portion.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read"
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-indexed, optional)"
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (inclusive, optional)"
            }
        },
        "required": ["path"]
    },
    "none"
)

TOOL_REGISTRY.register(
    "write_file",
    write_file,
    "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. Creates parent directories as needed.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "The full content to write to the file"
            }
        },
        "required": ["path", "content"]
    },
    "confirm"
)

TOOL_REGISTRY.register(
    "patch_file",
    patch_file,
    "Apply a search-and-replace edit to a file. Finds the exact 'search' text and replaces it with 'replace' text. More surgical than rewriting the whole file. Always read the file first to get exact text.",
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit"
            },
            "search": {
                "type": "string",
                "description": "Exact text to find in the file (must match exactly)"
            },
            "replace": {
                "type": "string",
                "description": "Text to replace the search text with"
            }
        },
        "required": ["path", "search", "replace"]
    },
    "confirm"
)

TOOL_REGISTRY.register(
    "bash",
    execute_bash,
    "Execute a shell command. On Windows uses cmd.exe, on Linux/Mac uses bash. Use this for running code, installing packages, git operations, etc. Returns stdout, stderr, and exit code.",
    {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)"
            }
        },
        "required": ["command"]
    },
    "confirm"
)

TOOL_REGISTRY.register(
    "glob_search",
    glob_search,
    "Search for files matching a glob pattern. Use '**/*.py' for recursive search, '*.txt' for current directory only.",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.py', '*.txt', 'src/**/*.js')"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)"
            }
        },
        "required": ["pattern"]
    },
    "none"
)

TOOL_REGISTRY.register(
    "grep",
    grep_search,
    "Search file contents for a regex pattern. Like 'grep -rn'. Returns matching lines with file paths and line numbers.",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)"
            },
            "include": {
                "type": "string",
                "description": "File pattern to include (e.g., '*.py')"
            }
        },
        "required": ["pattern"]
    },
    "none"
)

# Register web tools if available
if _has_web_tools:
    TOOL_REGISTRY.register(
        "web_search",
        web_search,
        "Search the web for information using DuckDuckGo.",
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)"
                }
            },
            "required": ["query"]
        },
        "none"
    )

    TOOL_REGISTRY.register(
        "fetch_page",
        fetch_page,
        "Fetch a web page and extract readable text content.",
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch"
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (default: 10000)"
                }
            },
            "required": ["url"]
        },
        "none"
    )