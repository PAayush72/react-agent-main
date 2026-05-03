# ReAct Coding Agent — Architecture & Flow

A terminal-based AI coding agent that uses a ReAct (Reason → Act → Observe) loop to understand and execute coding tasks. It connects to an MCP (Model Context Protocol) tool server and supports two LLM backends (SAP AI Hub, NVIDIA) with automatic fallback and real-time streaming.

---

## Quick Start

```bash
python main.py
```

The MCP server auto-starts automatically. If you prefer to run it manually:

```bash
# Terminal 1: Start the MCP tool server
python mcp_server.py

# Terminal 2: Run the agent
python main.py
```

---

## Architecture

```
User (CLI)
  │
  ▼
┌──────────────┐     async calls      ┌──────────────────┐
│   main.py    │ ────────────────────► │  core/agent.py   │
│  (Rich UI)   │                       │  (ReAct Loop)    │
│  + auto-MCP  │                       └───────┬──────────┘
└──────────────┘                               │
                                               │ call_model_stream()
                                               ▼
                                      ┌─────────────────┐
                                      │  llm_model.py   │
                                      │                 │
                                      │  1. SAP AI Hub  │ (streaming)
                                      │  2. NVIDIA API  │ (streaming, fallback)
                                      └─────────────────┘
                                               │
                          MCP calls            │
                              ▼                │
                       ┌─────────────────────┐
                       │   mcp_server.py     │
                       │   (FastMCP :8000)   │
                       │                     │
                       │  File Operations    │
                       │  Search Tools       │
                       │  Bash Execution     │
                       │  Web Tools          │
                       │  Chart Tools        │
                       │  Notebook Tools     │
                       └─────────────────────┘
```

### How It Works

1. **User types a message** in the CLI (`main.py`)
2. **main.py** auto-detects and starts the MCP server if not already running
3. **Agent** (`core/agent.py`) opens an MCP connection and discovers available tools
4. **ReAct loop** begins (max 50 steps):
   - **Reason**: Sends conversation history + tool schemas to the LLM via `call_model_stream()` (real-time streaming)
   - **Act**: If the LLM requests a tool call, the agent executes it via MCP
   - **Observe**: Tool results are fed back to the LLM
   - **Repeat** until the LLM responds with a final answer (no tool calls)
5. **Final response** is displayed as formatted text
6. **Loop detection**: Breaks if the same tool call is repeated 3x with identical params

---

## Project Structure

```
├── main.py                  # CLI entry point (Rich + prompt_toolkit, auto-MCP start)
├── llm_model.py             # LLM backend abstraction (SAP/NVIDIA streaming + fallback)
├── mcp_server.py            # MCP tool server (FastMCP, HTTP :8000, 18 tools)
├── Flow.md                  # This file — architecture documentation
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (API keys, gitignored)
│
├── core/
│   ├── __init__.py
│   └── agent.py             # Agent class (MCP-based ReAct loop, streaming, token tracking)
│
├── agents/
│   ├── __init__.py
│   └── sub_agent.py         # Sub-agent spawner (restricted tools, max depth 2)
│
├── context/
│   ├── __init__.py
│   └── compression.py       # Token-based context compression (truncation + summarization)
│
├── tests/
│   ├── __init__.py
│   ├── test_safety.py       # Bash safety + sandbox path tests
│   └── test_messages.py     # Message format builder tests
│
└── legacy/                  # Old commented-out code (preserved for reference)
```

---

## LLM Backends

The system uses a **cascading fallback chain** — it tries each backend in order until one succeeds. Both backends use **real-time streaming**.

| Priority | Backend | Env Var | Client | API |
|----------|---------|---------|--------|-----|
| 1 | **SAP AI Hub** | `DEPLOYMENT_ID` | `gen_ai_hub` (Bedrock) | `client.converse_stream()` |
| 2 | **NVIDIA** | `NVIDIA_API_KEY` | `openai.OpenAI` | `chat.completions.create(stream=True)` |

### Configuration (.env)

| Variable | Purpose |
|----------|---------|
| `DEPLOYMENT_ID` | SAP AI Hub deployment ID |
| `NVIDIA_API_KEY` | NVIDIA API key (fallback) |
| `NVIDIA_BASE_URL` | NVIDIA API endpoint (default: `https://integrate.api.nvidia.com/v1`) |
| `NVIDIA_MODEL` | NVIDIA model name (default: `qwen/qwen2.5-coder-32b-instruct`) |
| `TEMPERATURE` | Model temperature (default: `0.2`) |
| `MAX_TOKENS` | Max output tokens (default: `16384`) |

### Backend Selection

Use `/model` command to switch:
- `/model sap` — Force SAP AI Hub only
- `/model nvidia` — Force NVIDIA only
- `/model auto` — Automatic fallback (default)

---

## Tools

### Active Tools (via MCP Server)

All 19 tools are exposed through the MCP server at `localhost:8000`:

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_files` | `path` (default: `.`) | Lists directory contents with `[DIR]`/`[FILE]` indicators |
| `read_file` | `path`, `start_line?`, `end_line?` | Reads file with line numbers, supports line ranges |
| `write_file` | `path`, `content` | Writes content to file, creates parent directories |
| `patch_file` | `path`, `search`, `replace` | Surgical search-and-replace (single occurrence), shows diff |
| `delete_file` | `path` | Deletes a file (creates backup first) |
| `revert_file` | `path` | Reverts a file to its most recent backup, shows diff |
| `list_backups` | — | Lists all file backups with timestamps |
| `grep_search` | `pattern`, `path?`, `include?`, `max_results?` | Search for text patterns in files |
| `glob_search` | `pattern`, `path?` | Find files matching a glob pattern |
| `bash` | `command` | Executes shell commands (simple single commands only, no pipes/chains) |
| `web_search` | `query`, `max_results?` | DuckDuckGo web search |
| `fetch_page` | `url` | Fetches a webpage and extracts readable text |
| `generate_plotly_chart` | `data`, `chart_type?`, `title?`, `colors?` | Creates Plotly chart (bar/line/scatter/heatmap/histogram) + saves PNG |
| `smart_chart` | `user_query`, `data`, `colors?` | Infers chart type from natural language query |
| `generate_flow_diagram` | `spec` | Generates flow diagram from edge spec (e.g. `A->B; B->C`) |
| `search_and_chart` | `query`, `chart_type?`, `colors?` | Web search + chart generation suggestion |
| `generate_notebook` | `path`, `cells` | Creates Jupyter notebook from structured cell descriptions |
| `modify_notebook_cells` | `path`, `modifications` | Modifies existing notebook cells (replace/insert) |
| `generate_document_bundle` | `spec_json` | Generate DOCX/PDF/PPTX/HTML/Markdown documents from a JSON spec |

### Security

- **File sandbox**: All file paths are resolved relative to `BASE_DIR` (current working directory). Access outside is blocked.
- **Command safety**: Shell metacharacters (`;`, `|`, `&`, `` ` ``, `$`, `>`, `<`) are blocked to prevent command injection.
- **Command allowlist**: Only ~45 safe commands are allowed (`ls`, `cat`, `grep`, `git`, `python`, `curl`, etc.)
- **Dangerous pattern detection**: Regex blocks dangerous patterns (`rm -rf /`, `sudo`, `format`, `shutdown`, etc.)
- **Timeout**: Bash commands timeout after 120 seconds
- **Write tool approval**: User is prompted before write operations (`write_file`, `patch_file`, `delete_file`, `bash`)

---

## Message Flow (Detailed)

```
User: "Create a Python script that prints hello"
  │
  ▼
main.py
  │ _ensure_mcp_server() → auto-starts MCP if not running
  │ asyncio via _run_with_interrupt() → agent.chat("...")
  ▼
Agent.chat()
  │ Creates MCP Client("http://localhost:8000/mcp")
  │ async with mcp:
  │   └── _chat_loop()
  │       │
  │       ├── tool_defs = await self._get_tool_definitions(mcp)
  │       │   └── mcp.list_tools() → schemas for all tools
  │       │
  │       └── ReAct Loop (step 1..50):
  │           │
  │           ├── response = self._call_with_streaming(messages, tool_defs)
  │           │   │
  │           │   └── for chunk in call_model_stream(messages, tool_defs):
  │           │       │
  │           │       ├── Try SAP AI Hub (streaming)
  │           │       │   └── Yields StreamChunk(text/tool_start/tool_end/done)
  │           │       │
  │           │       ├── If SAP fails → Try NVIDIA (streaming)
  │           │       │   └── Yields StreamChunk(text/tool_start/tool_end/done)
  │           │       │
  │           │       └── Display: real-time text streaming to console
  │           │
  │           ├── If NO tool_calls:
  │           │   └── Return response.content (DONE)
  │           │
  │           ├── Loop detection: if same (tool_name, params) repeated 3x → break
  │           │
  │           └── If HAS tool_calls:
  │               ├── For each tool_call:
  │               │   ├── Normalize params (aliases: file_path → path)
  │               │   ├── Validate required params
  │               │   ├── await mcp.call_tool(name, params)
  │               │   │   └── MCP server executes tool function
  │               │   └── Display result in Panel
  │               │
  │               ├── Append tool_results to messages
  │               └── Loop back to _call_with_streaming()
  │
  └── Return final response
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/compact` | Compress context (truncates old messages + tool results, keeps last 6) |
| `/model` | Show current model or switch: `sap`, `nvidia`, `auto` |
| `/tokens` | Show token usage stats (input/output/total) |
| `/quit` | Exit the agent |
| `↑/↓` | Navigate command history |
| `Ctrl+C` | Cancel current operation (preserves context) |

---

## Streaming Architecture

The agent uses **real-time streaming** for both backends:

```
call_model_stream()
  │
  ├── _stream_sap() → Yields StreamChunk objects:
  │   ├── type="text"        → Token text (displayed immediately)
  │   ├── type="tool_start"  → Tool call beginning
  │   ├── type="tool_delta"  → Tool call argument fragment
  │   ├── type="tool_end"    → Tool call complete with params
  │   └── type="done"        → Final metadata (tokens, model, stop_reason)
  │
  └── _stream_nvidia() → Same StreamChunk types
      └── Handles multiple parallel tool calls (all indices)
```

The `call_model()` function exists as a **non-streaming wrapper** that consumes the stream for backward compatibility.

---

## Context Management

### Compression (`/compact`)

Uses `context/compression.py` — heuristic-based, no LLM calls:
1. **Truncates large tool results** in older messages (>2000 chars) — handles both `content` field and `results[].content`
2. **Removes old messages** keeping last 6 + system prompt
3. **Inserts summary placeholder** for removed messages
4. Token estimation: ~1 token ≈ 4 characters

### Conversation History

- Stored in-memory as a list of message dicts
- Roles: `system`, `user`, `assistant`, `tool_result`
- Cleared on `/clear` or session restart
- Ctrl+C cancellation preserves context

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | OpenAI-compatible client (for NVIDIA) |
| `fastmcp` | MCP server/client framework |
| `rich` | Terminal UI (panels, spinner, markdown, tables) |
| `prompt_toolkit` | CLI input with history |
| `python-dotenv` | .env file loading |
| `requests` | HTTP client (web tools) |
| `beautifulsoup4` | HTML parsing (web tools) |
| `duckduckgo-search` | Web search |
| `plotly` | Chart generation |
| `pandas` | Data manipulation for charts |
| `graphviz` | Flow diagram generation |
| `kaleido` | Plotly static image export |
| `nbformat` | Jupyter notebook creation/modification |

**Optional (SAP AI Hub):**
| `sap-ai-sdk-gen` | SAP AI Hub SDK (Bedrock proxy) |
| `boto3` | AWS SDK (Bedrock API) |
| `aiobotocore` | Async AWS SDK |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Known Issues / TODOs

- [ ] Persistent conversation history across sessions
- [ ] LLM-based context compression (summarization instead of truncation)
- [ ] Cost tracking per model backend
- [ ] Parallel tool execution
- [ ] Git-native workflow tools (branch, commit, PR)
- [ ] Session persistence and named sessions
