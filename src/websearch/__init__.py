#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from typing import Any, Dict, Optional

import azure.functions as func

from .service import perform_search, dumps_response


def _payload_from_request(req: func.HttpRequest) -> Dict[str, Any]:
    if req.method == "POST":
        try:
            return req.get_json() or {}
        except ValueError:
            return {}
    return {
        "query": req.params.get("q") or req.params.get("query"),
        "engines": (req.params.get("engines") or "").split(",") if req.params.get("engines") else None,
        "language": req.params.get("language"),
        "time_range": req.params.get("time_range"),
        "pageno": req.params.get("pageno"),
        "safesearch": req.params.get("safesearch"),
        "max_results": req.params.get("max_results"),
    }


def main(req: func.HttpRequest) -> func.HttpResponse:  # type: ignore[override]
    try:
        payload = _payload_from_request(req)
        response = perform_search(payload)
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
