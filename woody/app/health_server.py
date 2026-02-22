"""Minimal HTTP server for /health. Runs in a background thread."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


def _handler_factory():
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health" or self.path == "/health/":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress access logs
    return HealthHandler


def start_health_server(port: Optional[int] = None) -> None:
    """Start /health server in a daemon thread."""
    port = port or int(os.environ.get("WOODY_HEALTH_PORT", "9000"))
    server = HTTPServer(("0.0.0.0", port), _handler_factory())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
