# Installation Guide

## System Requirements

- Python 3.8 or higher
- pip (Python package manager)
- Git (for cloning the repository)
- Optional: Graphviz (for generating architecture diagrams)

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/react-agent-main.git
cd react-agent-main
```

### 2. Set Up Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Verify Installation

```bash
python main.py --help
```

You should see the help output showing available commands.

### 5. Initial Configuration

The agent comes with a built-in MCP server running on `http://localhost:8000/mcp`. No additional configuration is required to get started.

Example configuration is available in `mcp_config.example.json`.

## Quick Start

After installation, you can start using the agent immediately:

```bash
python main.py
```

You'll see the welcome message and can begin interacting with the agent.

## Troubleshooting Installation Issues

### Common Problems

1. **Python Version Too Old**
   - Error: "Python 3.8 or higher required"
   - Solution: Upgrade your Python installation

2. **Missing Dependencies**
   - Error: ModuleNotFoundError for specific packages
   - Solution: Run `pip install -r requirements.txt` again

3. **Permission Issues**
   - Error: Permission denied when installing packages
   - Solution: Use a virtual environment or add `--user` flag to pip

4. **Port Already in Use**
   - Error: Address already in use when starting built-in MCP server
   - Solution: Change the port in mcp_config.json or stop the conflicting service

## Development Installation

For developers who want to contribute:

```bash
# Fork and clone your fork
git clone https://github.com/yourusername/react-agent-main.git
cd react-agent-main

# Set up development environment
python -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest
```