from __future__ import annotations

import json
from typing import Any, Dict
import os
import sys
import glob
import logging
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Constants for the Azure Blob Storage container, file, and blob path
_SNIPPET_NAME_PROPERTY_NAME = "snippetname"
_SNIPPET_PROPERTY_NAME = "snippet"
_BLOB_PATH = "snippets/{mcptoolargs." + _SNIPPET_NAME_PROPERTY_NAME + "}.json"

def _ensure_dependencies_on_sys_path() -> None:
    app_root = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(app_root, ".python_packages", "lib", "site-packages"),
    ]
    # Fallback: try common virtualenv site-packages
    venv_lib_glob = os.path.join(app_root, ".venv", "lib", "python*", "site-packages")
    candidates.extend(glob.glob(venv_lib_glob))
    for candidate in candidates:
        if os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)


_ensure_dependencies_on_sys_path()

from websearch.service import perform_search, dumps_response

# Feature flag to enable/disable MCP generic triggers in environments
# where the custom binding may not be available (e.g., Azure).
_ENABLE_MCP_TRIGGERS = os.getenv("ENABLE_MCP_TRIGGERS", "false").lower() == "true"

class ToolProperty:
    def __init__(self, property_name: str, property_type: str, description: str):
        self.propertyName = property_name
        self.propertyType = property_type
        self.description = description

    def to_dict(self):
        return {
            "propertyName": self.propertyName,
            "propertyType": self.propertyType,
            "description": self.description,
        }


# Define the tool properties using the ToolProperty class
tool_properties_save_snippets_object = [
    ToolProperty(_SNIPPET_NAME_PROPERTY_NAME, "string", "The name of the snippet."),
    ToolProperty(_SNIPPET_PROPERTY_NAME, "string", "The content of the snippet."),
]

tool_properties_get_snippets_object = [
    ToolProperty(_SNIPPET_NAME_PROPERTY_NAME, "string", "The name of the snippet."),
]

# Convert the tool properties to JSON
tool_properties_save_snippets_json = json.dumps(
    [prop.to_dict() for prop in tool_properties_save_snippets_object]
)
tool_properties_get_snippets_json = json.dumps(
    [prop.to_dict() for prop in tool_properties_get_snippets_object]
)


if _ENABLE_MCP_TRIGGERS:
    @app.generic_trigger(
        arg_name="context",
        type="mcpToolTrigger",
        toolName="hello_mcp",
        description="Hello world.",
        toolProperties="[]",
    )
    def hello_mcp(context) -> None:
        return "Hello I am MCPTool!"


tool_properties_websearch_json = json.dumps([
    {
        "propertyName": "query",
        "propertyType": "string",
        "description": "Search query string"
    },
    {
        "propertyName": "max_results",
        "propertyType": "integer",
        "description": "Optional maximum number of results to return"
    }
])


if _ENABLE_MCP_TRIGGERS:
    @app.generic_trigger(
        arg_name="context",
        type="mcpToolTrigger",
        toolName="websearch",
        description="Meta web search using SearXNG.",
        toolProperties=tool_properties_websearch_json,
    )
    def mcp_websearch(context: str) -> str:
        content = json.loads(context) if context else {}
        arguments: Dict[str, Any] = content.get("arguments") or content

        payload: Dict[str, Any] = {
            "query": arguments.get("query"),
            "max_results": arguments.get("max_results"),
            "engines": arguments.get("engines"),
            "language": arguments.get("language"),
            "time_range": arguments.get("time_range"),
            "pageno": arguments.get("pageno"),
            "safesearch": arguments.get("safesearch"),
        }

        response = perform_search(payload)
        return dumps_response(response)


# HTTP route equivalent to the legacy /api/websearch endpoint
@app.route(route="websearch", methods=["GET", "POST"], auth_level=func.AuthLevel.FUNCTION)
def http_websearch(req: func.HttpRequest) -> func.HttpResponse:  # type: ignore[override]
    try:
        if req.method == "POST":
            try:
                content = req.get_json() or {}
            except ValueError:
                content = {}
        else:
            content = {
                "query": req.params.get("q") or req.params.get("query"),
                "engines": (req.params.get("engines") or "").split(",") if req.params.get("engines") else None,
                "language": req.params.get("language"),
                "time_range": req.params.get("time_range"),
                "pageno": req.params.get("pageno"),
                "safesearch": req.params.get("safesearch"),
                "max_results": req.params.get("max_results"),
            }

        response = perform_search(content)
        return func.HttpResponse(
            dumps_response(response),
            status_code=200,
            mimetype="application/json",
        )
    except ValueError as ve:
        return func.HttpResponse(
            json.dumps({"error": str(ve)}),
            status_code=400,
            mimetype="application/json",
        )
    except Exception as exc:  # pylint: disable=broad-except
        return func.HttpResponse(
            json.dumps({"error": "search_failed", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )


@app.route(route="ping", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def http_ping(req: func.HttpRequest) -> func.HttpResponse:  # type: ignore[override]
    return func.HttpResponse(
        json.dumps({"status": "ok"}),
        status_code=200,
        mimetype="application/json",
    )
