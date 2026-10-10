"""Offline diagnostic decisions, including independent failure and privacy cases."""

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "environment_diagnostics", Path(__file__).resolve().parents[2] / "scripts/diagnose.py"
)
assert spec and spec.loader
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
command_available = diagnostic.command_available


class EnvironmentDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.details = {
            "build": {"version": "fixture"},
            "database": "available",
            "redis": "available",
            "queues": {role: {"workers": 1} for role in ("interactive", "ingestion", "evaluation")},
            "chat_configuration": {
                role: {"credential_configured": True}
                for role in ("supervisor", "retriever", "analyst", "reviewer")
            },
            "corpus": {"state": "empty"},
        }
        self.responses = {
            "/api/health": {"status": "ok"},
            "/api/auth/status": {"initialized": True},
            "/api/diagnostics": self.details,
            "/api/providers/test": {"ok": True, "agent": "supervisor"},
        }
        patches = [
            patch.object(
                diagnostic,
                "request",
                side_effect=lambda port, path, **kw: self.responses.get(path, {}),
            ),
            patch.object(diagnostic, "command_available", return_value=True),
            patch.object(diagnostic.shutil, "which", return_value="docker"),
            patch.object(diagnostic, "port_state", return_value="occupied"),
        ]
        for selected in patches:
            selected.start()
            self.addCleanup(selected.stop)

    def states(self, **kwargs):
        return {check["code"]: check["state"] for check in diagnostic.diagnose(**kwargs)["checks"]}

    def test_normal_environment_does_not_claim_inference_or_nonempty_corpus(self):
        self.assertEqual(diagnostic.diagnose()["infrastructure"], "available")
        self.assertEqual(self.states()["inference_supervisor"], "not_tested")
        self.assertEqual(self.states()["corpus"], "empty")
        self.assertFalse(
            any(call.args[1] == "/api/providers/test" for call in diagnostic.request.call_args_list)
        )

    def test_docker_stopped_independently(self):
        diagnostic.command_available.side_effect = lambda args: args[1:] != ["info"]
        self.assertEqual(self.states()["docker_daemon"], "unavailable")
        self.assertEqual(self.states()["compose"], "available")

    def test_port_collision_and_absent_backend_independently(self):
        self.responses["/api/health"] = {}
        self.assertEqual(self.states()["backend_port"], "occupied")
        self.assertEqual(self.states()["backend"], "unavailable")
        self.assertEqual(self.states()["database"], "unknown")
        self.assertEqual(diagnostic.diagnose()["infrastructure"], "needs_attention")

    def test_database_unavailable_independently(self):
        self.details["database"] = "unavailable"
        self.assertEqual(self.states()["backend"], "available")
        self.assertEqual(self.states()["database"], "unavailable")
        self.assertEqual(diagnostic.diagnose()["infrastructure"], "needs_attention")

    def test_worker_unavailable_independently(self):
        self.details["queues"]["ingestion"]["workers"] = 0
        self.assertEqual(self.states()["database"], "available")
        self.assertEqual(self.states()["worker_ingestion"], "unavailable")
        self.assertEqual(diagnostic.diagnose()["infrastructure"], "needs_attention")

    def test_missing_models_independently(self):
        self.details["chat_configuration"]["analyst"]["credential_configured"] = False
        self.assertEqual(diagnostic.diagnose()["infrastructure"], "available")
        self.assertEqual(self.states(test_model=True)["models"], "not_configured")
        self.assertEqual(self.states(test_model=True)["inference_supervisor"], "not_tested")

    def test_auth_not_initialized_and_missing_access_are_unknown(self):
        self.responses["/api/auth/status"] = {"initialized": False}
        self.assertEqual(self.states()["local_auth"], "not_initialized")
        self.assertEqual(self.states()["models"], "unknown")
        self.responses["/api/auth/status"] = {"initialized": True}
        self.responses["/api/diagnostics"] = {}
        self.assertEqual(self.states()["database"], "unknown")

    def test_explicit_inference_only_and_failure(self):
        self.assertEqual(self.states(test_model=True)["inference_supervisor"], "succeeded")
        self.responses["/api/providers/test"] = {"ok": False}
        self.assertEqual(self.states(test_model=True)["inference_supervisor"], "failed")

    def test_report_does_not_echo_response_or_environment_secrets(self):
        secret = "SYNTHETIC_SECRET_NEVER_PRINT"
        self.details["unexpected"] = secret
        self.details["chat_configuration"]["analyst"]["provider"] = secret
        with patch.dict(diagnostic.os.environ, {"RAGAGENT_DIAGNOSTIC_TOKEN": secret}):
            report = json.dumps(diagnostic.diagnose())
        self.assertNotIn(secret, report)
        self.assertNotIn(
            secret, " ".join(str(check["advice"]) for check in diagnostic.diagnose()["checks"])
        )

    def test_raw_command_failures_are_not_printed(self):
        for error in (OSError("PRIVATE"), subprocess.TimeoutExpired("docker", 10)):
            with patch.object(diagnostic.subprocess, "run", side_effect=error):
                self.assertFalse(command_available(["docker", "info"]))


if __name__ == "__main__":
    unittest.main()
