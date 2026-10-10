"""Offline independent failure and data/secret protection checks, no Docker/model calls."""

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.local_deploy import DeployError, Deployment, private_write, update_env  # noqa: E402


class InstallationSafety(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "deployment"
        self.root.mkdir()
        self.backups = Path(self.temporary.name) / "backups"
        (self.root / ".env.example").write_text(
            "POSTGRES_PASSWORD=ragagent\nDATABASE_URL=postgresql+psycopg://ragagent:ragagent@db:5432/ragagent\nLOCAL_AUTH_TOKEN_HASH=\n"
        )
        (self.root / "scripts").mkdir()
        (self.root / "scripts/deployment_data.py").write_text("# owned helper fixture")
        self.deployment = Deployment(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_docker_has_safe_actionable_error(self):
        with patch("scripts.local_deploy.shutil.which", return_value=None):
            with self.assertRaisesRegex(DeployError, "docker_missing"):
                self.deployment.dependencies()

    def test_daemon_failure_never_prints_raw_secret_exception(self):
        with patch(
            "scripts.local_deploy.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, b"", b"API KEY SHOULD NOT ESCAPE"),
        ):
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaisesRegex(DeployError, "docker_not_running"):
                self.deployment.call(["docker", "info"], code="docker_not_running")
            self.assertEqual(output.getvalue(), "")

    def test_existing_configuration_is_preserved_across_restarts(self):
        existing = "POSTGRES_PASSWORD=old-private-db-password\nCUSTOM_EXISTING=value\n"
        (self.root / ".env").write_text(existing)
        self.deployment.initialize()
        self.deployment.initialize()
        self.assertEqual((self.root / ".env").read_text(), existing)

    def test_pair_rejects_raw_api_key_without_writing(self):
        with self.assertRaisesRegex(DeployError, "pairing_required"):
            self.deployment.pair("sk-live-secret-is-not-a-verifier")
        self.assertFalse((self.root / ".env").exists())

    def test_hash_pairing_preserves_password_and_does_not_store_bearer(self):
        self.deployment.initialize()
        password = (self.root / ".env").read_text().splitlines()[0]
        self.deployment.pair("a" * 64)
        self.assertIn(password, (self.root / ".env").read_text())
        self.assertIn("LOCAL_AUTH_TOKEN_HASH='" + "a" * 64, (self.root / ".env").read_text())

    def test_web_pair_stores_only_hash_and_preserves_desktop_pair(self):
        self.deployment.pair("a" * 64)
        web = "web-fixture-" + "w" * 52
        self.deployment.pair_web(web)
        saved = (self.root / ".env").read_text()
        self.assertNotIn(web, saved)
        self.assertIn("WEB_AUTH_TOKEN_HASH=", saved)
        self.assertIn("LOCAL_AUTH_TOKEN_HASH='" + "a" * 64, saved)
        with self.assertRaisesRegex(DeployError, "web_credential_invalid"):
            self.deployment.pair_web("short")

    def test_env_injection_and_symlink_are_rejected(self):
        path = self.root / "runtime.env"
        with self.assertRaisesRegex(DeployError, "configuration_invalid"):
            update_env(path, "OPENAI_API_KEY", "secret\nEVIL=1")
        if os.name != "nt":
            outside = self.root / "outside.txt"
            outside.write_text("retain me")
            path.symlink_to(outside)
            with self.assertRaisesRegex(DeployError, "secret_permissions"):
                private_write(path, "leak")
            self.assertEqual(outside.read_text(), "retain me")

    def test_secret_is_not_interpolated_and_permissions_are_private(self):
        path = self.root / "runtime.env"
        update_env(path, "OPENAI_API_KEY", "test-$DOLLAR-value")
        self.assertEqual(path.read_text(), "OPENAI_API_KEY='test-$DOLLAR-value'\n")
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_occupied_port_rejected_without_killing_process(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            occupied = listener.getsockname()[1]
            original = socket.socket

            class Collision:
                def __enter__(self):
                    self.socket = original()
                    return self

                def __exit__(self, *args):
                    self.socket.close()

                def bind(self, address):
                    self.socket.bind(("127.0.0.1", occupied))

            with (
                patch.object(self.deployment, "dc", return_value=b"[]"),
                patch("scripts.local_deploy.socket.socket", Collision),
            ):
                with self.assertRaisesRegex(DeployError, "port_conflict"):
                    self.deployment.ports()
            self.assertEqual(listener.getsockname()[1], occupied)

    def test_uninstall_never_deletes_data_or_configuration(self):
        self.deployment.initialize()
        before = (self.root / ".env").read_bytes()
        with patch.object(self.deployment, "dc", return_value=b"") as call:
            self.deployment.stop(uninstall=True)
        self.assertEqual(call.call_args.args, ("down", "--timeout", "120"))
        self.assertEqual((self.root / ".env").read_bytes(), before)

    def test_active_jobs_prevent_backup_and_upgrade(self):
        with patch.object(self.deployment, "dc", side_effect=DeployError("active_jobs")) as call:
            with self.assertRaisesRegex(DeployError, "active_jobs"):
                self.deployment.backup(self.backups)
            self.assertEqual(call.call_count, 1)
        self.assertFalse((self.backups).exists())

    def test_failed_dump_resumes_existing_services_without_upgrade(self):
        self.deployment.initialize()

        def command(*args, **kwargs):
            if "pg_dump" in args:
                raise DeployError("backup_failed")
            return b""

        with patch.object(self.deployment, "dc", side_effect=command) as call:
            with self.assertRaisesRegex(DeployError, "backup_failed"):
                self.deployment.backup(self.backups)
            self.assertEqual(call.call_args.args[0], "start")
            self.assertFalse(
                any("up" in item.args or "--build" in item.args for item in call.call_args_list)
            )

    def test_backup_excludes_secrets_and_preserves_nonsecret_model_settings(self):
        self.deployment.initialize()
        update_env(self.root / ".env", "OPENAI_API_KEY", "legacy-key-do-not-export")
        update_env(self.root / ".env", "UNRELATED_CREDENTIAL", "custom-secret-do-not-export")
        update_env(self.root / ".env", "SUPERVISOR_MODEL", "mock-model")
        private_write(
            self.root / ".runtime-secrets.env", "DEEPSEEK_API_KEY='secret-not-exported'\n"
        )

        def command(*args, **kwargs):
            if kwargs.get("output"):
                kwargs["output"].write_bytes(b"DEMO ONLY backup bytes")
            return b""

        with patch.object(self.deployment, "dc", side_effect=command):
            backup = self.deployment.backup(self.backups)
        settings = json.loads((backup / "settings.json").read_text())
        self.assertEqual(settings["SUPERVISOR_MODEL"], "'mock-model'")
        payload = "".join(path.read_text() for path in backup.iterdir())
        self.assertNotIn("legacy-key-do-not-export", payload)
        self.assertNotIn("custom-secret-do-not-export", payload)
        self.assertNotIn("secret-not-exported", payload)
        self.assertNotIn("DATABASE_URL", settings)
        self.assertTrue((backup / "backup-manifest.json").exists())

    def test_corrupt_backup_is_rejected_before_docker_mutation(self):
        with patch.object(self.deployment, "dc") as call:
            with self.assertRaisesRegex(DeployError, "backup_invalid"):
                self.deployment.restore(self.root, confirm_empty=True)
        call.assert_not_called()

    def test_web_proxy_failure_cannot_report_installation_ready(self):
        required = [
            "api",
            "db",
            "redis",
            "worker-interactive",
            "worker-ingestion",
            "worker-evaluation",
            "frontend",
        ]
        status = json.dumps([{"Service": name, "State": "running"} for name in required]).encode()
        with (
            patch("scripts.local_deploy.urllib.request.build_opener") as client,
            patch.object(self.deployment, "dc", return_value=status),
        ):
            local = client.return_value.open.return_value.__enter__.return_value
            local.read.return_value = b'{"status":"ready"}'
            client.return_value.open.side_effect = [
                client.return_value.open.return_value,
                OSError("proxy unavailable"),
            ]
            with self.assertRaisesRegex(DeployError, "not_ready"):
                self.deployment.ready(timeout=0)

    def test_all_three_workers_required_for_readiness(self):
        with (
            patch("scripts.local_deploy.urllib.request.build_opener") as client,
            patch.object(
                self.deployment,
                "dc",
                return_value=b'[{"Service":"api","State":"running"},{"Service":"db","State":"running"}]',
            ),
        ):
            client.return_value.open.return_value.__enter__.return_value.read.return_value = (
                b'{"status":"ready"}'
            )
            with self.assertRaisesRegex(DeployError, "not_ready"):
                self.deployment.ready(timeout=0)


if __name__ == "__main__":
    unittest.main()
