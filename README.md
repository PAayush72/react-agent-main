# ReAct Coding Agent

A terminal-based AI coding assistant that uses a **ReAct** (Reason → Act → Observe) loop to understand and execute coding tasks. It connects to an MCP (Model Context Protocol) tool server and supports multiple LLM backends with automatic fallback and real-time streaming.

## Features

- **Real-time streaming** responses from the LLM
- **Automatic fallback** between SAP AI Hub and NVIDIA backends
- **19 built-in tools**: file operations, code search, bash execution, web search, chart generation, notebook creation, and more
- **File sandboxing**: all file operations restricted to working directory
- **Command safety**: allowlist + shell injection prevention + dangerous pattern detection
- **Auto-backup**: file modifications are automatically backed up with diffs
- **Loop detection**: prevents infinite tool-call loops
- **Token tracking**: real-time input/output token usage stats
- **Context compression**: automatic truncation of old tool results

---

## Prerequisites

- **Python 3.10+** (tested on 3.10)
- **pip** (Python package manager)
- **graphviz** system package (for flow diagram generation, optional)

### Install graphviz (system dependency)

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install -y graphviz
```

**macOS:**
```bash
brew install graphviz
```

**Windows:**
Download from [graphviz.org](https://graphviz.org/download/) and add to PATH.

---

## Quick Start (5 minutes)

### 1. Clone the repository

```bash
git clone https://github.com/PAayush72/react-agent-main.git
cd react-agent-main
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up your API key

Get a **free** NVIDIA API key from [build.nvidia.com](https://build.nvidia.com/):

1. Sign up / log in
2. Go to any model page (e.g. Qwen 3.5)
3. Click "Get API Key"
4. Copy the key (starts with `nvapi-`)

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Then edit `.env` and paste your key:

```env
NVIDIA_API_KEY=nvapi-your_key_here
```

That's it. You only need one API key to get started.

### 5. Run the agent

```bash
python main.py
```

The MCP server starts automatically. Start typing your coding tasks.

---

## Full Setup Guide

### Step-by-Step from Zero

#### Step 1: Check Python version

```bash
python3 --version
```

Must be **3.10 or higher**. If not, install it:

**Ubuntu/Debian:**
```bash
sudo apt install python3.10 python3.10-venv
```

**macOS:**
```bash
brew install python@3.10
```

#### Step 2: Install graphviz (system package)

This is required for the flow diagram tool. The agent works without it, but `generate_flow_diagram` will fail.

```bash
# Ubuntu/Debian
sudo apt install -y graphviz

# macOS
brew install graphviz
```

#### Step 3: Clone and set up the project

```bash
git clone https://github.com/PAayush72/react-agent-main.git
cd react-agent-main
```

#### Step 4: Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` in your terminal prompt.

#### Step 5: Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs all core dependencies. The SAP AI Hub SDK is **optional** and commented out by default.

#### Step 6: Configure API keys

Copy the example environment file:

```bash
cp .env.example .env
```

Open `.env` in any text editor and add your API key(s):

**Minimum — NVIDIA only (recommended for most users):**
```env
NVIDIA_API_KEY=nvapi-your_key_here
```

**Optional — Add SAP AI Hub for fallback:**
```env
NVIDIA_API_KEY=nvapi-your_key_here
DEPLOYMENT_ID=your_sap_deployment_id
```

#### Step 7: (Optional) Enable SAP AI Hub backend

If you have access to SAP AI Hub and want to use it as the primary backend:

1. Install the SAP packages:
   ```bash
   pip install sap-ai-sdk-gen boto3 aiobotocore
   ```

2. Add your `DEPLOYMENT_ID` to `.env`

---

## Running the Agent

### Simple Start (Recommended)

```bash
source .venv/bin/activate
python main.py
```

The MCP server starts automatically in the background.

### Manual Start (Two Terminals)

If you prefer to manage the MCP server separately:

**Terminal 1 — MCP Server:**
```bash
source .venv/bin/activate
python mcp_server.py
```

**Terminal 2 — Agent:**
```bash
source .venv/bin/activate
python main.py
```

---

## Usage

Once the agent starts, you'll see a welcome banner. Type your coding task:

```
> Create a Python script that reads a CSV file and prints the first 5 rows
```

The agent will:
1. Think about the task
2. Use tools as needed (read files, write files, run commands)
3. Show you each tool call and its result
4. Return a final answer

### CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/clear` | Clear conversation history |
| `/compact` | Compress context to save tokens |
| `/model` | Show or change the LLM backend (`sap`, `nvidia`, `auto`) |
| `/tokens` | Show token usage stats (input/output/total) |
| `/quit` | Exit the agent |
| `↑ / ↓` | Navigate previous questions |
| `Ctrl+C` | Cancel current operation (keeps context) |

### Model Selection

```
> /model          # Show current model
> /model sap      # Force SAP AI Hub
> /model nvidia   # Force NVIDIA
> /model auto     # Automatic fallback (default)
```

---

## Available Tools

The agent has access to these tools through the MCP server:

### File Operations
| Tool | Description |
|------|-------------|
| `list_files` | List directory contents with file sizes |
| `read_file` | Read a file (with optional line range) |
| `write_file` | Write content to a file (auto-backup) |
| `patch_file` | Surgical search-and-replace with diff |
| `delete_file` | Delete a file (auto-backup) |
| `revert_file` | Revert a file to its last backup |
| `list_backups` | List all file backups |

### Search
| Tool | Description |
|------|-------------|
| `grep_search` | Search for text patterns in files (case-insensitive) |
| `glob_search` | Find files matching a glob pattern |

### Execution
| Tool | Description |
|------|-------------|
| `bash` | Run shell commands (single commands only, no pipes/chains) |

### Web
| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo web search |
| `fetch_page` | Fetch and extract webpage text |

### Charts & Diagrams
| Tool | Description |
|------|-------------|
| `generate_plotly_chart` | Create charts (bar/line/scatter/heatmap/histogram) |
| `smart_chart` | Create charts from natural language queries |
| `generate_flow_diagram` | Generate flow diagrams from edge specs |
| `search_and_chart` | Web search + chart suggestion |

### Notebooks
| Tool | Description |
|------|-------------|
| `generate_notebook` | Create Jupyter notebooks |
| `modify_notebook_cells` | Modify existing notebook cells |

---

## Architecture

```
User (CLI) → main.py → core/agent.py (ReAct Loop)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              llm_model.py    mcp_server.py    context/
              (SAP/NVIDIA)    (18 tools)      compression
```

See [Flow.md](Flow.md) for detailed architecture documentation.

---

## Project Structure

```
├── main.py                  # CLI entry point
├── llm_model.py             # LLM backend (SAP/NVIDIA streaming)
├── mcp_server.py            # MCP tool server (18 tools)
├── Flow.md                  # Architecture documentation
├── requirements.txt         # Python dependencies
│
├── core/
│   └── agent.py             # ReAct loop agent
├── agents/
│   └── sub_agent.py         # Sub-agent spawner
├── context/
│   └── compression.py       # Context compression
└── tests/
    ├── test_safety.py       # Bash safety + sandbox tests
    └── test_messages.py     # Message format tests
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Troubleshooting

### pip install fails on sap-ai-sdk-gen

This is a **proprietary SAP package** and is **optional**. The project works fine with just NVIDIA. The SAP packages are commented out in `requirements.txt` by default.

### MCP server won't start

- Check if port 8000 is already in use: `lsof -i :8000` or `netstat -tlnp | grep 8000`
- Kill any existing process: `kill <pid>`
- The agent auto-detects running MCP servers and won't start a duplicate

### "All model backends failed"

- Verify your `.env` file has at least one valid API key
- Check network connectivity to the API endpoints
- Try forcing a specific backend: `/model nvidia`

### Graphviz errors

- Make sure the system `graphviz` package is installed (not just the Python package)
- On Linux: `sudo apt install graphviz`
- On macOS: `brew install graphviz`

### Import errors

- Ensure you're in the virtual environment: `source .venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

---

## License

This project is released under the [MIT License](LICENSE).
