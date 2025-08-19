import os
import random
import time
import httpx
from httpx import Timeout, Limits, HTTPTransport

# --- Config via variables d'env ---
# Timeout de lecture global pour les appels sortants (10–15s conseillé en cloud)
READ_TIMEOUT = float(os.getenv("SEARX_OUTGOING_TIMEOUT", "12"))
# Taille du pool de connexions
MAX_CONN = int(os.getenv("SEARX_HTTP_MAX_CONNECTIONS", "100"))
MAX_KEEPALIVE = int(os.getenv("SEARX_HTTP_MAX_KEEPALIVE", "50"))
# Forcer IPv4 si l'IPv6/DNS est bancal (true/false)
FORCE_IPV4 = os.getenv("SEARX_FORCE_IPV4", "true").lower() in ("1", "true", "yes")
# Jitter en millisecondes entre tirs (évite fan-out trop sync)
JITTER_MS = int(os.getenv("SEARX_REQUEST_JITTER_MS", "0"))

limits = Limits(max_connections=MAX_CONN, max_keepalive_connections=MAX_KEEPALIVE)
transport = HTTPTransport(
    # astuce: binder en IPv4 pour forcer l'usage d'AF_INET
    local_address="0.0.0.0" if FORCE_IPV4 else None,
    retries=2,  # retries réseau idempotents
)

# Client global réutilisé par toute l'app
CLIENT = httpx.Client(
    timeout=Timeout(connect=5.0, read=READ_TIMEOUT, write=5.0, pool=READ_TIMEOUT),
    limits=limits,
    transport=transport,
    headers={"User-Agent": os.getenv("SEARX_USER_AGENT", "searxng-func/1.0")},
)

def jitter():
    if JITTER_MS > 0:
        time.sleep(random.uniform(0, JITTER_MS) / 1000.0)

def http_get(url: str, **kwargs) -> httpx.Response:
    """GET avec client global + éventuel jitter."""
    jitter()
    return CLIENT.get(url, **kwargs)

def http_post(url: str, **kwargs) -> httpx.Response:
    """POST avec client global + éventuel jitter."""
    jitter()
    return CLIENT.post(url, **kwargs)
