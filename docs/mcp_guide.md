# MCP Server Management Guide

## Overview

The agent supports Model Context Protocol (MCP) servers to extend its capabilities beyond built-in tools. You can configure both HTTP-based and STDIO-based MCP servers through simple slash commands.

## MCP Server Types

### HTTP MCP Servers
Connect to MCP servers over HTTP/S:
```
/mcp add weather-server http://weather-api.example.com/mcp
```

### STDIO MCP Servers
Connect to MCP servers via standard input/output:
```
/mcp add filesystem-server npx @modelcontextprotocol/server-filesystem /tmp
/mcp add python-server python /path/to/mcp_server.py --port 3001
```

## MCP Commands

### List Servers
View all configured MCP servers with their status:
```
/mcp list
```

Sample output:
```
┌─────────────────┬────────┬──────────┬──────────────────────────────┐
│ Name            │ Type   │ Status   │ Description                  │
├─────────────────┼────────┼──────────┼──────────────────────────────┤
│ built-in        │ HTTP   │ enabled  │ Internal MCP server          │
│ weather-server  │ HTTP   │ enabled  │ Weather data MCP server      │
│ filesystem      │ STDIO  │ disabled │ File system access server    │
└─────────────────┴────────┴──────────┴──────────────────────────────┘
```

### Add Server
Add a new MCP server configuration:
```
/mcp add <name> <url|command> [args...]
```

Examples:
```
# HTTP server
/mcp add my-api https://api.example.com/mcp

# STDIO server with arguments
/mcp add my-server python /path/to/server.py --debug --port 8080
```

### Enable/Disable Server
Toggle server status without removing configuration:
```
/mcp enable <name>
/mcp disable <name>
```

### Remove Server
Delete an MCP server configuration (built-in server protected):
```
/mcp remove <name>
```

Note: The built-in server cannot be removed.

### Reload Configuration
Apply configuration changes:
```
/mcp reload
```

Use this after adding, enabling, disabling, or removing servers to activate changes.

### List Available Tools
See all tools from all connected servers:
```
/mcp tools
```

Sample output:
```
Available Tools (3 total):
  • read_file (filesystem) - Read file contents
  • write_file (filesystem) - Write file contents
  • get_weather (weather-server) - Get weather information
```

## Configuration File

MCP server configurations are stored in `mcp_config.json`:

```json
{
  "mcpServers": {
    "built-in": {
      "url": "http://localhost:8000/mcp",
      "enabled": true
    },
    "weather-server": {
      "url": "http://weather-api.example.com/mcp",
      "enabled": true,
      "description": "Weather data MCP server"
    },
    "filesystem": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "enabled": false,
      "description": "File system access server"
    }
  }
}
```

## Tool Naming and Conflicts

When multiple servers provide the same tool name:
- The first server in the configuration list takes precedence
- Conflicting tools from later servers are skipped with a warning
- Use `/mcp tools` to see which server provides each tool
- Reorder or disable servers to resolve conflicts as needed

## Examples

### Adding a Weather Service
```
/mcp add weather-api https://api.weather.com/mcp
/mcp reload
```

Then use its tools:
```
What's the current temperature in New York?
```

### Adding a Local Filesystem Server
```
/mcp add local-fs npx @modelcontextprotocol/server-filesystem /home/user/documents
/mcp reload
```

Then use its tools:
```
List the files in my documents folder
Read the contents of notes.txt
```

### Using Multiple Servers
Configure multiple specialized servers:
```
/mcp add weather https://weather-api.example.com/mcp
/mcp add finance https://finance-api.example.com/mcp
/mcp add local-files npx @modelcontextprotocol/server-filesystem /projects
/mcp reload
```

Access tools from any server:
```
What's the forecast for London?
What's AAPL's stock price today?
Show me the README file in my projects folder
```

## Best Practices

1. **Descriptive Names**: Use clear, meaningful names for your MCP servers
2. **Test Connections**: Verify servers work with `/mcp list` after adding
3. **Monitor Status**: Check server status regularly, especially for external services
4. **Resource Management**: Disable unused servers to conserve resources
5. **Security**: Only add trusted MCP servers, especially those with file/system access
6. **Documentation**: Keep track of what each server provides for easier troubleshooting

## Troubleshooting

### Server Shows as Disconnected
1. Verify the server URL or command is correct
2. Check network connectivity for HTTP servers
3. Ensure the command exists and is executable for STDIO servers
4. Look at server logs if available
5. Use `/mcp reload` after fixing connection issues

### Tool Not Available
1. Check if the server is enabled with `/mcp list`
2. Verify the server shows as connected
3. Use `/mcp tools` to confirm the tool is listed
4. Check for naming conflicts with other servers
5. Reload connections with `/mcp reload`

### Configuration Issues
1. Validate JSON syntax in mcp_config.json
2. Ensure required fields (url or command) are present
3. Check that arguments are properly formatted as arrays
4. Restart the agent if configuration corruption is suspected

## Limitations

1. **Built-in Protection**: The built-in MCP server cannot be removed
2. **First-Wins Conflict Resolution**: Duplicate tools use the first server's implementation
3. **Timeout Connections**: Connections timeout after 15 seconds of inactivity
4. **Environment Variables**: Limited support for custom environment variables in STDIO servers