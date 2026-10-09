"""Executable platform smoke against a synthetic loopback API, never a paid model."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FixtureAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/health":
            payload = {"status": "ok"}
        elif self.path == "/api/auth/status":
            payload = {"initialized": True}
        elif self.path == "/api/diagnostics":
            payload = {
                "build": {"version": "SYNTHETIC PLATFORM FIXTURE"},
                "database": "available",
                "redis": "available",
                "queues": {
                    role: {"workers": 1} for role in ("interactive", "ingestion", "evaluation")
                },
                "chat_configuration": {
                    role: {"credential_configured": False}
                    for role in ("supervisor", "retriever", "analyst", "reviewer")
                },
                "corpus": {"state": "empty"},
                "untrusted_extra": "SYNTHETIC_SECRET_NEVER_PRINT",
            }
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureAPI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = str(server.server_port)
    if sys.platform == "win32":
        command = [
            "pwsh",
            "-NoProfile",
            "-File",
            str(ROOT / "scripts/diagnose.ps1"),
            "-Json",
            "-Port",
            port,
        ]
    else:
        command = [str(ROOT / "scripts/diagnose.sh"), "--json", "--port", port]
    commands = [command]
    if sys.platform == "win32":
        commands.append(["powershell", *command[1:]])
    try:
        for selected in commands:
            result = subprocess.run(
                selected, capture_output=True, text=True, timeout=60, check=False
            )
            assert result.returncode == 0, "launcher failed; raw output withheld"
            report = json.loads(result.stdout)
            states = {check["code"]: check["state"] for check in report["checks"]}
            assert states["backend_port"] == "occupied"
            assert states["models"] == "not_configured"
            assert states["inference_supervisor"] == "not_tested"
            assert "SYNTHETIC_SECRET_NEVER_PRINT" not in result.stdout + result.stderr
        server.shutdown()
        server.server_close()
        for selected in commands:
            stopped = subprocess.run(
                selected, capture_output=True, text=True, timeout=60, check=False
            )
            assert stopped.returncode == 1
            assert json.loads(stopped.stdout)["infrastructure"] == "needs_attention"
        print(
            f"{sys.platform}: executable launcher PASS "
            "(synthetic API, stopped backend, port occupancy, unconfigured models, "
            "no inference/secret output)"
        )
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
