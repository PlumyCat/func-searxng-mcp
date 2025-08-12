# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

import azure.functions as func

import searx  # triggers settings initialization
import searx.engines
import searx.preferences
import searx.webadapter
import searx.search
import searx.plugins
from searx.enginelib import Engine


_SEARCH_INITIALIZED: bool = False


def _initialize_search_core() -> None:
    global _SEARCH_INITIALIZED
    if _SEARCH_INITIALIZED:
        return
    # Initialize engines, network and processors with metrics disabled
    searx.search.initialize(
        settings_engines=searx.settings["engines"],
        enable_checker=False,
        check_network=False,
        enable_metrics=False,
    )
    _SEARCH_INITIALIZED = True


def _build_form(payload: Dict[str, Any]) -> Dict[str, str]:
    form: Dict[str, str] = {}
    # required
    form["q"] = str(payload.get("query", "")).strip()
    # optional mapping with sane defaults
    if engines := payload.get("engines"):
        if isinstance(engines, list):
            form["engines"] = ",".join([str(e) for e in engines])
        elif isinstance(engines, str):
            form["engines"] = engines
    if lang := payload.get("language"):
        form["language"] = str(lang)
    if pageno := payload.get("pageno"):
        form["pageno"] = str(pageno)
    if time_range := payload.get("time_range"):
        form["time_range"] = str(time_range)
    if safe := payload.get("safesearch"):
        form["safesearch"] = str(safe)
    return form


def _strip_transient(result: Dict[str, Any]) -> Dict[str, Any]:
    # Remove fields not intended for clients
    result.pop("parsed_url", None)
    return result


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return str(obj)
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


def main(req: func.HttpRequest) -> func.HttpResponse:  # type: ignore[override]
    _initialize_search_core()

    try:
        if req.method == "POST":
            try:
                payload = req.get_json() or {}
            except ValueError:
                payload = {}
        else:
            payload = {
                "query": req.params.get("q") or req.params.get("query"),
                "engines": (req.params.get("engines") or "").split(",") if req.params.get("engines") else None,
                "language": req.params.get("language"),
                "time_range": req.params.get("time_range"),
                "pageno": req.params.get("pageno"),
                "safesearch": req.params.get("safesearch"),
                "max_results": req.params.get("max_results"),
            }

        form = _build_form(payload)
        if not form.get("q"):
            return func.HttpResponse(
                json.dumps({"error": "Missing required field: query"}),
                status_code=400,
                mimetype="application/json",
            )

        # Preferences minimal setup
        engine_categories = list(searx.engines.categories.keys())
        engines_map: dict[str, Engine] = cast(dict[str, Engine], searx.engines.engines)
        preferences = searx.preferences.Preferences(["simple"], engine_categories, engines_map, searx.plugins.STORAGE)

        search_query = searx.webadapter.get_search_query_from_webapp(preferences, form)[0]
        result_container = searx.search.Search(search_query).search()

        results = result_container.get_ordered_results()
        max_results: Optional[int] = None
        try:
            if payload.get("max_results") is not None:
                max_results = int(payload["max_results"])  # type: ignore[index]
        except Exception:
            max_results = None
        if isinstance(max_results, int) and max_results > 0:
            results = results[:max_results]

        results_json: List[Dict[str, Any]] = []
        for r in results:
            rd = r.as_dict()  # MainResult | LegacyResult both implement as_dict()
            rd.pop("parsed_url", None)
            results_json.append(rd)

        response = {
            "search": {
                "q": search_query.query,
                "pageno": search_query.pageno,
                "lang": search_query.lang,
                "safesearch": search_query.safesearch,
                "timerange": search_query.time_range,
            },
            "results": results_json,
            "infoboxes": result_container.infoboxes,
            "suggestions": list(result_container.suggestions),
            "answers": list(result_container.answers),
            "paging": result_container.paging,
            "number_of_results": result_container.number_of_results,
        }

        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False, default=_json_default),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as exc:  # pylint: disable=broad-except
        # Return minimal error detail without leaking request context
        return func.HttpResponse(
            json.dumps({"error": "search_failed", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )


