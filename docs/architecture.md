# Agent Architecture Documentation

## System Architecture Overview

```mermaid
flowchart TD
    A[User Input] --> B[main.py CLI]
    B --> C[Agent Core]
    C --> D[MCP Manager]
    D --> E[Tool Execution]
    E --> F[Results]
    F --> G[User Output]
    H[Built-in MCP Server] --> D
    I[External MCP Servers] --> D
    J[Configuration] --> D
    K[Logging] --> C
```

### Component Descriptions

| Component | Description |
|-----------|-------------|
| **main.py CLI** | Command-line interface that processes user input and slash commands |
| **Agent Core** | Central orchestration loop that manages the ReAct reasoning process |
| **MCP Manager** | Handles MCP server connections, tool discovery, and request routing |
| **Tool Execution** | Executes tools (both built-in and MCP-provided) |
| **Results** | Processed outputs from tool executions |
| **User Output** | Formatted responses displayed to the user |
| **Built-in MCP Server** | Internal server providing agent's native capabilities (runs on http://localhost:8000/mcp) |
| **External MCP Servers** | User-configured external MCP servers (HTTP or STDIO) |
| **Configuration** | MCP server settings loaded from mcp_config.json |
| **Logging** | System logging for debugging and monitoring |

## Data Flow Diagrams

### Basic Request Processing Flow

```mermaid
sequenceDiagram
    participant U as User
    participant M as main.py CLI
    participant A as Agent Core
    participant MP as MCP Manager
    participant S as MCP Server
    
    U->>M: Enter command/query
    alt Slash Command
        M->>M: Process command (help, mcp, etc.)
        M-->>U: Return result
    else Agent Query
        M->>A: Pass query to agent
        loop ReAct Process
            A->>MP: Request tool execution
            MP->>S: Route to appropriate server
            S-->>MP: Return tool results
            MP-->>A: Return results to agent
            A->>A: Think/Reason about results
        end
        A-->>M: Return final response
        M-->>U: Display formatted response
    end
```

### MCP Server Connection Flow

```mermaid
flowchart LR
    subgraph Startup
        MCP[MCP Manager] --> CFG[Load mcp_config.json]
        CFG --> HS{Server Type}
        HS -->|HTTP| HC[Create HTTP Client]
        HS -->|STDIO| SC[Spawn Process]
        HC --> DC[Discover Tools]
        SC --> DC
        DC --> TR[Register in Tool Registry]
    end
    
    subgraph Runtime
        TR --> TE[Tool Execution Request]
        TE --> RS[Route to Server]
        RS --> HS
        HS -->|HTTP| HC
        HS -->|STDIO| SC
        HC --> EX[Execute Tool]
        SC --> EX
        EX --> RS
        RS --> TR
    end
```

### Configuration Update Flow

```mermaid
sequenceDiagram
    participant U as User
    participant M as main.py CLI
    participant F as File System
    participant MP as MCP Manager
    
    U->>M: /mcp add <server> <url>
    M->>F: Update mcp_config.json
    M-->>U: Confirm addition
    U->>M: /mcp reload
    M->>MP: Signal reload
    MP->>F: Read updated config
    MP->>MP: Remove disabled servers
    MP->>MP: Add/enable new servers
    MP->>MP: Refresh tool registry
    MP-->>M: Confirm reload complete
    M-->>U: Show updated server list
```

## Key Features

### 1. MCP Server Management
- Supports both HTTP and STDIO MCP server types
- Dynamic addition/removal without restart
- Built-in server protection (cannot be removed)
- Conflict resolution (first server wins for duplicate tools)

### 2. Tool Routing
- Centralized MCP Manager handles all tool requests
- Transparent routing to appropriate server
- Consistent interface regardless of server type
- Error handling and fallback mechanisms

### 3. Configuration Persistence
- JSON-based configuration (mcp_config.json)
- Example configuration provided (mcp_config.example.json)
- Runtime updates through slash commands
- Validation and error reporting

### 4. Extensibility
- Easy to add new MCP servers
- Standard MCP protocol compliance
- Community tool sharing capability
- Future-proof design

## Security Considerations

1. **Built-in Server Protection**: Cannot be removed via MCP commands
2. **Input Validation**: All MCP commands validate parameters
3. **Process Isolation**: STDIO servers run in separate processes
4. **Network Safety**: HTTP servers only connect to configured endpoints
5. **Tool Sandboxing**: MCP protocol limits tool capabilities