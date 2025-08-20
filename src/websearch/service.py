# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, cast

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
        import searx as _searx  # type: ignore  # noqa: I001
        import searx.engines as _searx_engines  # noqa: F401
        import searx.preferences as _searx_preferences  # noqa: F401
        import searx.webadapter as _searx_webadapter  # noqa: F401
        import searx.search as _searx_search  # noqa: F401
        import searx.plugins as _searx_plugins  # noqa: F401
        from searx.enginelib import Engine as _Engine  # type: ignore
        searx = _searx
        Engine = _Engine
        
        # Test import of commonly failing dependencies
        try:
            import dateutil
            print(f"DEBUG: dateutil imported successfully from {dateutil.__file__}")
        except ImportError as e:
            print(f"DEBUG: dateutil import failed: {e}")
            
        try:
            import babel
            print(f"DEBUG: babel imported successfully from {babel.__file__}")
        except ImportError as e:
            print(f"DEBUG: babel import failed: {e}")
            
    except Exception as exc:  # pragma: no cover
        print(f"DEBUG: SearXNG core import failed: {exc}")
        import sys
        print(f"DEBUG: sys.path = {sys.path}")
        raise RuntimeError(f"Failed to import SearXNG core: {exc}") from exc
    _harden_settings(searx)
    searx.search.initialize(
        settings_engines=searx.settings["engines"],
        enable_checker=False,
        check_network=False,
        enable_metrics=False,
    )
    _SEARCH_INITIALIZED = True


def _test_engine_imports() -> set[str]:
    """Test which engines can be imported successfully."""
    working_engines = set()
    
    # Test some basic engines that usually work
    basic_engines = ["google", "bing", "startpage", "brave", "mojeek"]
    
    for engine_name in basic_engines:
        try:
            # Try to import the engine module
            import importlib
            module = importlib.import_module(f"searx.engines.{engine_name}")
            working_engines.add(engine_name)
            print(f"DEBUG: Engine {engine_name} imported successfully")
        except Exception as e:
            print(f"DEBUG: Engine {engine_name} failed to import: {e}")
    
    return working_engines

def _harden_settings(searx_mod) -> None:
    """Tune SearXNG at runtime sans modifier le YAML."""
    s = searx_mod.settings
    outgoing = s.setdefault("outgoing", {})
    outgoing["request_timeout"] = float(os.getenv("REQUEST_TIMEOUT", "2.5"))
    outgoing["max_request_timeout"] = float(os.getenv("MAX_REQUEST_TIMEOUT", "6"))
    
    # Test which engines work and disable the rest
    working_engines = _test_engine_imports()
    
    # Désactiver des engines problématiques si présents
    to_disable = {
        e.strip().lower()
        for e in os.getenv(
            "DISABLE_ENGINES",
            "wikipedia,wikidata,github,stackoverflow,hackernews,duckduckgo,qwant",
        ).split(",")
    }
    
    for eng in s.get("engines", []):
        name = str(eng.get("name", "")).lower()
        # Disable if explicitly in disable list OR if it failed import test
        if name in to_disable or (name not in working_engines and name not in ["google", "bing", "startpage", "brave", "mojeek"]):
            eng["disabled"] = True
            print(f"DEBUG: Disabled engine {name}")
        else:
            print(f"DEBUG: Keeping engine {name} enabled")


def _build_form(payload: dict[str, Any]) -> dict[str, str]:
    form: dict[str, str] = {}
    form["q"] = str(payload.get("query", "")).strip()
    # Engines par défaut si non fournis - utiliser seulement les engines simples qui fonctionnent
    default_engines = os.getenv(
        "DEFAULT_ENGINES",
        "google,bing,startpage,brave",
    )
    engines = payload.get("engines") or default_engines
    if engines:
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


def perform_search(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a search using SearXNG core based on the given payload.

    Expected payload keys: query (str), engines (list[str]|str), language (str),
    time_range (str), pageno (int), safesearch (int), max_results (int).

    The returned dictionary includes an ``unresponsive_engines`` field listing
    engines that failed to respond. Each entry contains the engine name and the
    error type encountered.
    """
    # Try SearXNG first, but fallback to simple search if it fails
    try:
        return _perform_searxng_search(payload)
    except Exception as e:
        print(f"SearXNG search failed, using fallback: {e}")
        # Import here to avoid circular imports
        from .simple_search import perform_simple_search
        return perform_simple_search(payload)


def _perform_searxng_search(payload: dict[str, Any]) -> dict[str, Any]:
    """Original SearXNG search implementation."""
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
    max_results: int | None = None
    try:
        if payload.get("max_results") is not None:
            max_results = int(payload["max_results"])  # type: ignore[index]
    except Exception:
        max_results = None
    if isinstance(max_results, int) and max_results > 0:
        results = results[:max_results]

    results_json: list[dict[str, Any]] = []
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
    
    # If no results and all engines failed, raise exception to trigger fallback
    if not results_json and response["unresponsive_engines"]:
        raise RuntimeError("All SearXNG engines failed")
    
    return response


def dumps_response(response: dict[str, Any]) -> str:
    return json.dumps(response, ensure_ascii=False, default=_json_default)
