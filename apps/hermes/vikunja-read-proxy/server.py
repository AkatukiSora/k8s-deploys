#!/usr/bin/env python3
"""Read-only facade for the loopback Vikunja adapter; it never sees its token."""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

ADAPTER_BASE_URL = "http://127.0.0.1:8791"
MAX_RESPONSE_BYTES = 32 * 1024
ALLOWED_QUERY = {"page", "per_page", "s"}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None: pass
    def send_json(self, status: int, value: object) -> None:
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz": self.send_json(200, {"status":"ok"}); return
        routes = {"/v1/projects":"/projects", "/v1/tasks":"/tasks"}
        if parsed.path not in routes: self.send_json(404, {"error":"route not found"}); return
        query = parse_qs(parsed.query, keep_blank_values=False)
        if set(query) - ALLOWED_QUERY or any(len(v) != 1 for v in query.values()): self.send_json(400, {"error":"unsupported query parameter"}); return
        suffix = "?" + urlencode({k:v[0] for k,v in query.items()}) if query else ""
        try:
            request = Request(ADAPTER_BASE_URL + routes[parsed.path] + suffix, headers={"Accept":"application/json"}, method="GET")
            with urlopen(request, timeout=10) as response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES: self.send_json(502, {"error":"adapter response exceeded size limit"}); return
                self.send_response(response.status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)
        except HTTPError as error: self.send_json(error.code if error.code in {400,404,503} else 502, {"error":"adapter request failed"})
        except (URLError, TimeoutError, OSError): self.send_json(503, {"error":"adapter unavailable"})
    def do_POST(self) -> None: self.send_json(405, {"error":"method not allowed"})
    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

def main() -> None: ThreadingHTTPServer(("0.0.0.0", 8793), Handler).serve_forever()
if __name__ == "__main__": main()
