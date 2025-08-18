# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

# Lazy-loaded SearXNG modules to avoid import-time failures on Azure
searx = None  # type: ignore[assignment]
Engine = None  # type: ignore[assignment]


_SEARCH_INITIALIZED: bool = False


def _initialize_search_core() -> None:
    global _SEARCH_INITIALIZED
    global searx
    global Engine
    if _SEARCH_INITIALIZED:
        return
    try:
        # Import here to avoid loading at module import time
        import searx as _searx  # type: ignore
        import searx.engines as _searx_engines  # noqa: F401
        import searx.preferences as _searx_preferences  # noqa: F401
        import searx.webadapter as _searx_webadapter  # noqa: F401
        import searx.search as _searx_search  # noqa: F401
        import searx.plugins as _searx_plugins  # noqa: F401
        from searx.enginelib import Engine as _Engine  # type: ignore
        searx = _searx
        Engine = _Engine
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to import SearXNG core: {exc}") from exc
    searx.search.initialize(
        settings_engines=searx.settings["engines"],
        enable_checker=False,
        check_network=False,
        enable_metrics=False,
    )
    _SEARCH_INITIALIZED = True


def _build_form(payload: Dict[str, Any]) -> Dict[str, str]:
    form: Dict[str, str] = {}
    form["q"] = str(payload.get("query", "")).strip()
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


def perform_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run a search using SearXNG core based on the given payload.

    Expected payload keys: query (str), engines (list[str]|str), language (str),
    time_range (str), pageno (int), safesearch (int), max_results (int).

    The returned dictionary includes an ``unresponsive_engines`` field listing
    engines that failed to respond. Each entry contains the engine name and the
    error type encountered.
    """
    _initialize_search_core()

    form = _build_form(payload)
    if not form.get("q"):
        raise ValueError("Missing required field: query")

    engine_categories = list(searx.engines.categories.keys())  # type: ignore[attr-defined]
    engines_map: dict[str, Engine] = cast(
        dict[str, Engine], searx.engines.engines)  # type: ignore[attr-defined]
    preferences = searx.preferences.Preferences(  # type: ignore[attr-defined]
        ["simple"], engine_categories, engines_map, searx.plugins.STORAGE)  # type: ignore[attr-defined]

    search_query = searx.webadapter.get_search_query_from_webapp(preferences, form)[  # type: ignore[attr-defined]
        0]
    result_container = searx.search.Search(search_query).search()  # type: ignore[attr-defined]

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
        rd = r.as_dict()
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
    response["unresponsive_engines"] = [
        {"engine": u.engine, "error": u.error_type}
        for u in result_container.unresponsive_engines
    ]
    return response


def dumps_response(response: Dict[str, Any]) -> str:
    return json.dumps(response, ensure_ascii=False, default=_json_default)
