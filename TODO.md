MCP WebSearch Azure Function — Migration Plan

Scope and outcomes
- Transform the repository into a minimal backend-only service usable as an MCP-style websearch tool, exposed via an Azure HTTP Function.
- Keep SearXNG’s engine, query parsing, and aggregation core. Remove UI, assets, and features that imply stateful storage or analytics.

What we keep (core)
- `searx/engines`, `searx/search`, `searx/network`, `searx/query`, `searx/webadapter`, `searx/preferences`, `searx/settings_loader`, `searx/settings.yml`, and supporting utilities strictly required by the search flow.

What we drop or disable (no UI, no state, no analytics)
- Remove: front-end (templates, static, Vite client) and root `package.json` used for UI build.
- Do not use: Redis/Valkey limiter, openmetrics/metrics, stats endpoints, bot detection. Keep code present if needed for import stability, but do not initialize or call it in the Azure Function.
- No persistent storage or collected data; no anonymization layer since nothing is stored.

Deliverable: Azure HTTP Function (MCP-style websearch)
- Input (JSON body or querystring): `{ "query": string, "max_results"?: number, "engines"?: string[], "language"?: string, "time_range"?: "day|week|month|year" }`
- Output (JSON): `{ "results": Array<Result>, "answers": string[], "suggestions": string[], "paging": any, "number_of_results": number }` where `Result` includes the SearXNG result fields minus internal/transient fields.
- No metrics, no counters, no cookies, no user tracking; only minimal function logs.

Tasks
1) Scaffold Azure Function (done)
   - `host.json` at repo root
   - `websearch/function.json` and `websearch/__init__.py`
   - Disable metrics via `searx.search.initialize(..., enable_metrics=False)`

2) Map request to SearXNG core (done)
   - Build a `Preferences` and use `searx.webadapter.get_search_query_from_webapp` to create a `SearchQuery`
   - Execute search using `searx.search.Search(search_query).search()`

3) Shape response for MCP-style tool (done)
   - Return JSON-only, remove transient fields (e.g., `parsed_url`)

4) Remove UI and build assets (done)
   - Deleted: `client/`, `searx/templates/`, `searx/static/`, root `package.json`

5) Configuration and dependencies
   - Use existing `requirements.txt` for now; add `azure-functions` to it if deploying Functions directly from this repo. Consider a minimal `requirements-azure.txt` in a follow-up.
   - Keep `settings.yml` to manage engines; avoid engines that require secrets unless provided via environment variables.

6) Privacy and compliance (done/minimal)
   - No persistence or metrics
   - Minimal logging of operational errors only

7) Tests
   - Add unit test for the function handler (`websearch/__init__.py`) to validate input→output mapping and ensure no state is written.

8) Deployment
   - Provide a short README with Azure Functions deployment steps (func core tools, or Azure Portal/CLI).

Open questions / later improvements
- Provide a minimal curated `settings.yml` for engines that work without API keys in serverless environments.
- Optionally add a small transform to match any evolving MCP websearch schema exactly.


