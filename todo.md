Parfait. Voilà un **patch minimal** prêt à appliquer qui :

* ajoute un **client HTTPX global** (pool, timeouts configurables, **IPv4 forcé** optionnel),
* expose un endpoint **/api/netcheck** pour diagnostiquer DNS/egress,
* fournit un **helper** à utiliser dans tes appels moteurs (remplace tes `requests.get(...)` / `httpx.Client()` ad-hoc).

Tu peux coller ce bloc dans ton repo (à la racine) avec `git apply` :

```diff
*** Begin Patch
*** Add File: src/common/http_client.py
+import os
+import random
+import time
+import httpx
+from httpx import Timeout, Limits, HTTPTransport
+
+# --- Config via variables d'env ---
+# Timeout de lecture global pour les appels sortants (10–15s conseillé en cloud)
+READ_TIMEOUT = float(os.getenv("SEARX_OUTGOING_TIMEOUT", "12"))
+# Taille du pool de connexions
+MAX_CONN = int(os.getenv("SEARX_HTTP_MAX_CONNECTIONS", "100"))
+MAX_KEEPALIVE = int(os.getenv("SEARX_HTTP_MAX_KEEPALIVE", "50"))
+# Forcer IPv4 si l'IPv6/DNS est bancal (true/false)
+FORCE_IPV4 = os.getenv("SEARX_FORCE_IPV4", "true").lower() in ("1", "true", "yes")
+# Jitter en millisecondes entre tirs (évite fan-out trop sync)
+JITTER_MS = int(os.getenv("SEARX_REQUEST_JITTER_MS", "0"))
+
+limits = Limits(max_connections=MAX_CONN, max_keepalive_connections=MAX_KEEPALIVE)
+transport = HTTPTransport(
+    # astuce: binder en IPv4 pour forcer l'usage d'AF_INET
+    local_address="0.0.0.0" if FORCE_IPV4 else None,
+    retries=2,  # retries réseau idempotents
+)
+
+# Client global réutilisé par toute l'app
+CLIENT = httpx.Client(
+    timeout=Timeout(connect=5.0, read=READ_TIMEOUT, write=5.0, pool=READ_TIMEOUT),
+    limits=limits,
+    transport=transport,
+    headers={"User-Agent": os.getenv("SEARX_USER_AGENT", "searxng-func/1.0")},
+)
+
+def jitter():
+    if JITTER_MS > 0:
+        time.sleep(random.uniform(0, JITTER_MS) / 1000.0)
+
+def http_get(url: str, **kwargs) -> httpx.Response:
+    """GET avec client global + éventuel jitter."""
+    jitter()
+    return CLIENT.get(url, **kwargs)
+
+def http_post(url: str, **kwargs) -> httpx.Response:
+    """POST avec client global + éventuel jitter."""
+    jitter()
+    return CLIENT.post(url, **kwargs)
+
*** End Patch
```

```diff
*** Begin Patch
*** Add File: src/functions/netcheck.py
+import json
+import socket
+import azure.functions as func
+from common.http_client import CLIENT
+
+app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
+
+@app.function_name(name="netcheck")
+@app.route(route="netcheck", methods=[func.HttpMethod.GET])
+def netcheck(req: func.HttpRequest) -> func.HttpResponse:
+    report = {}
+    try:
+        # DNS IPv4 (AF_INET)
+        report["dns_A_duckduckgo"] = socket.getaddrinfo("duckduckgo.com", 443, socket.AF_INET)
+    except Exception as e:
+        report["dns_A_error"] = repr(e)
+    try:
+        # DNS IPv6 (AF_INET6) — peut échouer si IPv6/DNS est cassé (OK)
+        report["dns_AAAA_duckduckgo"] = socket.getaddrinfo("duckduckgo.com", 443, socket.AF_INET6)
+    except Exception as e:
+        report["dns_AAAA_error"] = repr(e)
+    try:
+        r1 = CLIENT.get("https://1.1.1.1/cdn-cgi/trace", timeout=5.0)
+        r2 = CLIENT.get("https://duckduckgo.com/?q=hello", timeout=10.0)
+        report["http_1_1_1_1"] = r1.status_code
+        report["http_duckduckgo"] = r2.status_code
+    except Exception as e:
+        report["http_error"] = repr(e)
+    return func.HttpResponse(json.dumps(report, default=str), mimetype="application/json")
+
*** End Patch
```

```diff
*** Begin Patch
*** Update File: requirements.txt
@@
-# (tes dépendances existantes)
+httpx>=0.27.0
*** End Patch
```

```diff
*** Begin Patch
*** Update File: local.settings.json
@@
   "IsEncrypted": false,
   "Values": {
     "AzureWebJobsStorage": "UseDevelopmentStorage=true",
     "FUNCTIONS_WORKER_RUNTIME": "python",
+    // --- Réglages réseau/HTTP conseillés ---
+    "SEARX_OUTGOING_TIMEOUT": "12",
+    "SEARX_FORCE_IPV4": "true",
+    "SEARX_HTTP_MAX_CONNECTIONS": "100",
+    "SEARX_HTTP_MAX_KEEPALIVE": "50",
+    "SEARX_REQUEST_JITTER_MS": "0"
   }
 }
*** End Patch
```

### Comment l’utiliser dans tes appels moteurs

Remplace tes appels réseau ponctuels par le helper :

```python
# AVANT (exemples)
# r = requests.get(url, timeout=3)
# with httpx.Client() as c: r = c.get(url, timeout=3)

# APRÈS
from common.http_client import http_get, http_post
r = http_get(engine_url, params={"q": query}, timeout=None)  # timeout global déjà appliqué
```

> Le **client global** gère pool/retries + IPv4 forcé (si `SEARX_FORCE_IPV4=true`).
> Tu peux aussi définir `SEARX_REQUEST_JITTER_MS=100` pour lisser les rafales (fan-out).

---

## Étapes rapides

```bash
git checkout -b fix/http-global-ipv4
git apply patch.diff   # (ou colle les blocs ci-dessus via 'git apply <<EOF ... EOF')
pip install -r requirements.txt
func start
curl http://localhost:7071/api/netcheck
```

* Si `http_duckduckgo` et `http_1_1_1_1` répondent (200/301), l’egress est OK.
* Tes **timeouts “engine … after 3.00s”** devraient disparaître (ou nettement baisser).
* Ajuste `SEARX_OUTGOING_TIMEOUT` (10–15s recommandé en Function) si besoin.

Si tu veux, je peux aussi te fournir un **patch optionnel** qui **limite le nombre d’engines par requête** (ex. `SEARX_MAX_ENGINES=6`) et applique un petit **jitter** entre tirs — utile si tu touches des limites SNAT/concurrence.
