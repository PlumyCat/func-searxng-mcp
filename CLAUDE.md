# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Azure Functions Python v2 project that implements an MCP (Model Context Protocol) server with web search capabilities. The application provides both HTTP endpoints and optional MCP tool triggers backed by SearXNG search engine.

## Core Architecture

- **Azure Functions**: Python v2 programming model using decorators (no `function.json` files)
- **MCP Integration**: Optional MCP tool triggers via experimental extension bundle
- **SearXNG Backend**: Full SearXNG search engine integrated as a library for web search
- **Blob Storage**: Azure Blob Storage for snippet management (optional MCP tools)

### Key Components

- `src/function_app.py`: Main Azure Function app with HTTP routes and MCP triggers
- `src/websearch/service.py`: SearXNG integration service with lazy loading
- `src/searx/`: Complete SearXNG search engine library
- `infra/`: Bicep templates for Azure infrastructure

## Common Development Commands

### Local Development
```bash
# Install dependencies
cd src && pip install -r requirements.txt

# Start local development server
func start

# Start with specific host/port
func start --host 0.0.0.0 --port 7071
```

### Azure Deployment
```bash
# Initialize project (if not already done)
azd init -t remote-mcp-functions-python

# Deploy infrastructure and code
azd up

# Deploy code only (after initial provisioning)
azd deploy

# Clean up Azure resources
azd down
```

### Testing Endpoints
```bash
# Health check (anonymous)
curl -s "http://localhost:7071/api/ping"

# Web search (requires function key in production)
curl -s "http://localhost:7071/api/websearch?query=test"

# With POST request
curl -s -X POST "http://localhost:7071/api/websearch" \
  -H "Content-Type: application/json" \
  -d '{"query": "azure functions", "max_results": 3}'
```

### Getting Azure Configuration
```bash
# Get function app name and resource group from AZD environment
FUNCTION_APP_NAME=$(cat .azure/$(cat .azure/config.json | jq -r '.defaultEnvironment')/env.json | jq -r '.FUNCTION_APP_NAME')
RESOURCE_GROUP=$(cat .azure/$(cat .azure/config.json | jq -r '.defaultEnvironment')/env.json | jq -r '.AZURE_RESOURCE_GROUP')

# Get function keys
az functionapp keys list -g $RESOURCE_GROUP -n $FUNCTION_APP_NAME
```

## Code Conventions

### Import Strategy
- SearXNG modules are lazy-loaded in `websearch/service.py` to prevent import failures on Azure
- Use `_initialize_search_core()` before any SearXNG operations

### Environment Variables
Key environment variables in `local.settings.json`:
- `ENABLE_MCP_TRIGGERS`: "true" to enable MCP tools (default: "false")
- `DEFAULT_ENGINES`: Default search engines to use
- `DISABLE_ENGINES`: Engines to disable (comma-separated)
- `REQUEST_TIMEOUT`: Search request timeout in seconds
- `MAX_REQUEST_TIMEOUT`: Maximum timeout for requests

### MCP Tools
When MCP triggers are enabled (`ENABLE_MCP_TRIGGERS=true`):
- `hello_mcp`: Simple hello world tool
- `websearch`: Web search using SearXNG
- Optional snippet tools (save_snippet, get_snippet) available but not currently registered

## Azure Function Configuration

### host.json
- Uses experimental extension bundle for MCP support
- Application Insights sampling configured

### Function Auth Levels
- `/api/ping`: Anonymous access
- `/api/websearch`: Function-level authentication required
- MCP triggers: System key required (`mcp_extension`)

## SearXNG Configuration

### Runtime Settings Hardening
The `_harden_settings()` function in `websearch/service.py`:
- Sets request timeouts based on environment variables
- Disables problematic engines (Google, Bing by default)
- Uses safe default engines (qwant, wikipedia)

### Search Response Format
Responses include:
- `results`: Array of search results
- `unresponsive_engines`: Array of engines that failed with error types
- `search`: Query metadata (language, safesearch, etc.)
- `suggestions`, `answers`, `infoboxes`: Additional search data

## Development Notes

- **No package.json**: This is a Python project, dependencies are in `requirements.txt`
- **Bicep Infrastructure**: All Azure resources defined in `infra/` directory
- **VS Code Integration**: MCP configuration in `.vscode/mcp.json` for VS Code Copilot
- **Local Storage**: Uses Azurite for local blob storage development
- **Git Safety**: Includes `searx/version_frozen.py` to avoid git calls at runtime

## Troubleshooting

### Function Import Errors
If functions "disappear" after deployment, check for module-level import errors. SearXNG imports are deferred to avoid this issue.

### MCP Connection Issues
- Verify `ENABLE_MCP_TRIGGERS=true` is set
- Check system key `mcp_extension` is properly configured
- Ensure experimental extension bundle is enabled in `host.json`

### Search Engine Issues
- Check `DISABLE_ENGINES` environment variable
- Verify `DEFAULT_ENGINES` are accessible
- Review timeout settings (`REQUEST_TIMEOUT`, `MAX_REQUEST_TIMEOUT`)