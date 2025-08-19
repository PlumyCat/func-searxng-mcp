import json
import socket
import azure.functions as func
from common.http_client import CLIENT

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.function_name(name="netcheck")
@app.route(route="netcheck", methods=[func.HttpMethod.GET])
def netcheck(req: func.HttpRequest) -> func.HttpResponse:  # type: ignore[override]
    report = {}
    try:
        # DNS IPv4 (AF_INET)
        report["dns_A_duckduckgo"] = socket.getaddrinfo("duckduckgo.com", 443, socket.AF_INET)
    except Exception as e:  # pylint: disable=broad-except
        report["dns_A_error"] = repr(e)
    try:
        # DNS IPv6 (AF_INET6) — peut échouer si IPv6/DNS est cassé (OK)
        report["dns_AAAA_duckduckgo"] = socket.getaddrinfo("duckduckgo.com", 443, socket.AF_INET6)
    except Exception as e:  # pylint: disable=broad-except
        report["dns_AAAA_error"] = repr(e)
    try:
        r1 = CLIENT.get("https://1.1.1.1/cdn-cgi/trace", timeout=5.0)
        r2 = CLIENT.get("https://duckduckgo.com/?q=hello", timeout=10.0)
        report["http_1_1_1_1"] = r1.status_code
        report["http_duckduckgo"] = r2.status_code
    except Exception as e:  # pylint: disable=broad-except
        report["http_error"] = repr(e)
    return func.HttpResponse(json.dumps(report, default=str), mimetype="application/json")
