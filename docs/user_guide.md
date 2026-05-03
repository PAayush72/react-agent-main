# User Guide

## Getting Started

Once installed, start the agent by running:

```bash
python main.py
```

You'll see a welcome message and a prompt where you can enter commands or ask questions.

## Basic Usage

### Asking Questions

Simply type your question or request at the prompt:

```
What is the capital of France?
How do I make a chocolate cake?
Explain quantum computing in simple terms.
```

The agent will process your request using its built-in capabilities and any configured MCP servers.

### Using Slash Commands

Slash commands provide additional functionality and configuration options:

```
/help          - Show available commands
/mcp list      - List configured MCP servers
/mcp add <name> <url> - Add an HTTP MCP server
/mcp add <name> <command> [args...] - Add an STDIO MCP server
/mcp enable <name> - Enable an MCP server
/mcp disable <name> - Disable an MCP server
/mcp remove <name> - Remove an MCP server (built-in protected)
/mcp reload    - Reload MCP configuration
/mcp tools     - List all available tools from all servers
```

## MCP Server Management

### Adding HTTP MCP Servers

To add an HTTP-based MCP server:

```
/mcp add my-server http://example.com/mcp
```

### Adding STDIO MCP Servers

To add a server that communicates via standard input/output:

```
/mcp add my-python-server python /path/to/server.py
/mcp add my-node-server node /path/to/server.js --port 3000
```

### Managing Server States

Enable/disable servers without removing them:

```
/mcp disable my-server
/mcp enable my-server
```

### Removing Servers

Remove servers you no longer need:

```
/mcp remove old-server
```

Note: The built-in server cannot be removed for security and functionality reasons.

### Reloading Configuration

After making changes through direct file edits or if you want to apply changes:

```
/mcp reload
```

## Available Tools

To see all tools available from configured servers:

```
/mcp tools
```

This will show a list of tools with their descriptions and which server provides them.

## Examples

### Using Built-in Tools

The agent comes with built-in tools for common tasks:

```
What's the weather like in New York?
Calculate 15% tip on a $42.50 meal.
What's the current date and time?
```

### Using External MCP Servers

After configuring an external server with specialized tools:

```
/mcp add weather-server http://weather-api.example.com/mcp
/mcp reload
```

Then you can use its tools:

```
What's the forecast for Tokyo next weekend?
Is it going to rain in London tomorrow?
```

## Tips and Best Practices

1. **Start Simple**: Begin with the built-in capabilities before adding external servers
2. **Test Connections**: Use `/mcp list` to verify server status after adding
3. **Monitor Tools**: Use `/mcp tools` to see what capabilities you have available
4. **Organize Servers**: Use descriptive names for your MCP servers
5. **Regular Updates**: Periodically check for updates to external MCP servers
6. **Backup Config**: Consider backing up your mcp_config.json after configuration

## Troubleshooting

### Server Connection Issues

If a server shows as disconnected:
1. Verify the URL or command is correct
2. Check network connectivity for HTTP servers
3. Ensure the command exists and is executable for STDIO servers
4. Check server logs if available
5. Use `/mcp reload` after fixing issues

### Tool Conflicts

When two servers provide the same tool:
- The first server in the configuration list takes precedence
- Use `/mcp tools` to see which server provides each tool
- Reorder or disable servers to resolve conflicts as needed

### Performance Issues

If the agent seems slow:
1. Check if any MCP servers are experiencing delays
2. Consider disabling unused servers
3. Verify network connections to external servers
4. Check server resource usage

## Advanced Usage

### Chaining Requests

You can reference previous results in follow-up questions:

```
What's the population of Japan?
Now compare it to Germany's population.
```

### Context Awareness

The agent maintains context across multiple interactions within a session.

### Custom Instructions

You can provide context or instructions that affect how the agent processes your requests:

```
When answering technical questions, explain as if I'm a beginner.
```

This guidance will be used for subsequent requests in the same session.