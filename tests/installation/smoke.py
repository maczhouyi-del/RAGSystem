"""Actual Docker/API/PG/Redis/RQ/native Docling test; chat/vector models MOCK.

SYNTHETIC ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED.
Run only in CI's owned empty Compose project. Never against a user's corpus.
"""

import hashlib
import http.cookiejar
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.local_deploy import DeployError, Deployment, update_env  # noqa: E402
from scripts.pdf_fixture import write_provenance_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
AUTH = os.environ["LOCAL_AUTH_TOKEN"]
CLIENT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, data=None, *, method=None, multipart=False):
    headers = {"Authorization": "Bearer " + AUTH}
    if data is not None:
        headers["Content-Type"] = (
            "multipart/form-data; boundary=rag-installation-fixture"
            if multipart
            else "application/json"
        )
        data = data if multipart else json.dumps(data).encode()
    with CLIENT.open(
        urllib.request.Request(
            "http://127.0.0.1:8000" + path, data=data, headers=headers, method=method
        ),
        timeout=20,
    ) as response:
        body = response.read()
        return (
            json.loads(body)
            if "application/json" in response.headers.get("Content-Type", "")
            else body
        )


def wait(run):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        current = request("/api/runs/" + run["id"])
        if current["status"] not in ("queued", "running"):
            assert current["status"] == "completed", current.get("error_code")
            return current
        time.sleep(1)
    raise AssertionError("actual_worker_timeout")


def stage(name):
    print("Installation stage:", name, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write("\nInstallation engineering / MOCK stage: " + name + "\n")


def main():
    stage("infrastructure_and_runtime_configuration")
    deployment = Deployment(ROOT, overlay=ROOT / "tests/installation/compose.mock.yaml")
    deployment.ready()
    # Fixed engineering-only sentinel, never a real key or paid provider call.
    sentinel = "ENGINEERING-MOCK-NOT-A-REAL-API-KEY"
    update_env(ROOT / ".runtime-secrets.env", "OPENAI_API_KEY", sentinel)
    web = "installation-web-" + "w" * 48
    deployment.pair_web(web)
    deployment.start(build=False)
    browser = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    with browser.open(
        urllib.request.Request(
            "http://127.0.0.1:8080/api/auth/session",
            data=b"",
            headers={"Authorization": "Bearer " + web},
        ),
        timeout=10,
    ) as response:
        assert "HttpOnly" in response.headers["Set-Cookie"]
    with browser.open("http://127.0.0.1:8080/api/auth/status", timeout=10) as response:
        assert json.load(response)["authenticated"]
    providers = request("/api/providers")
    assert all(agent["key_configured"] for agent in providers["agents"].values())
    assert sentinel not in json.dumps(request("/api/diagnostics"))
    assert sentinel not in json.dumps(providers)
    assert (
        request("/api/providers", {"agents": providers["agents"]}, method="PUT")["status"]
        == "saved"
    )
    with tempfile.TemporaryDirectory() as temporary:
        pdf = Path(temporary) / "owned.pdf"
        write_provenance_pdf(pdf)
        original = pdf.read_bytes()
        payload = (
            b"--rag-installation-fixture\r\nContent-Disposition: form-data; name="
            b'"title"\r\n\r\nDEMO ONLY / NOT A BENCHMARK\r\n--rag-installation-fixtur'
            b'e\r\nContent-Disposition: form-data; name="file"; filename="owned.p'
            b'df"\r\nContent-Type: application/pdf\r\n\r\n'
            + original
            + b"\r\n--rag-installation-fixture--\r\n"
        )
        stage("real_native_docling_pdf_import_and_index")
        uploaded = request("/api/papers/upload", payload, multipart=True)
        wait(uploaded)
        pid = uploaded["paper_id"]
        paper = request("/api/papers/" + pid)
        assert paper["status"] == "indexed" and paper["chunk_count"] > 0
        assert request("/api/papers/" + pid + "/pdf") == original
        runs = []
        for mode in ("rag", "research"):
            stage("mock_" + mode + "_and_exports")
            field = "query" if mode == "rag" else "research_question"
            result = wait(
                request(
                    "/api/rag/query" if mode == "rag" else "/api/research",
                    {
                        field: "Quote original source text on page one.",
                        "filters": {"paper_ids": [pid]},
                    },
                )
            )
            runs.append(result["id"])
            report = request("/api/runs/" + result["id"] + "/exports/report.md")
            assert b"Original source text on page one." in report
            for name in ("comparison.csv", "references.bib", "citations.json"):
                assert request("/api/runs/" + result["id"] + "/exports/" + name)
        # Real worker failure, health failure, and recovery, without deleting anything.
        for service in ("worker-ingestion", "db"):
            stage("failure_and_recovery_" + service)
            deployment.dc("stop", service)
            try:
                deployment.ready(timeout=0)
            except DeployError as error:
                assert str(error) == "not_ready"
            else:
                raise AssertionError("stopped_dependency_reported_ready")
            deployment.dc("start", service)
            deployment.ready()
        stage("quiesced_backup")
        backup = deployment.backup(Path(temporary) / "backups")
        assert (
            hashlib.sha256(request("/api/papers/" + pid + "/pdf")).digest()
            == hashlib.sha256(original).digest()
        )
        # In-place migration and container recreation must preserve indexed data/config/history.
        stage("restart_and_migration_preserve_data")
        deployment.stop()
        deployment.start(build=False)
        with browser.open("http://127.0.0.1:8080/api/auth/status", timeout=10) as response:
            assert not json.load(response)["authenticated"]
        with browser.open(
            urllib.request.Request(
                "http://127.0.0.1:8080/api/auth/session",
                data=b"",
                headers={"Authorization": "Bearer " + web},
            ),
            timeout=10,
        ) as response:
            assert json.load(response)["authenticated"]
        assert request("/api/providers")["agents"] == providers["agents"]
        assert request("/api/papers/" + pid)["status"] == "indexed"
        for rid in runs:
            assert request("/api/runs/" + rid)["status"] == "completed"
        deployment.stop(uninstall=True)
        volumes = deployment.call(["docker", "volume", "ls", "--format", "{{.Name}}"]).decode()
        assert all(
            "scientific-ragagent_" + name in volumes
            for name in ("postgres", "redis", "papers", "config", "models")
        )
        # Restore into an explicitly isolated empty project; original volumes remain untouched.
        restored_root = Path(temporary) / "restore"
        restored_root.mkdir()
        import shutil

        for name in ("compose.yaml", ".env.example"):
            shutil.copy2(ROOT / name, restored_root / name)
        (restored_root / "scripts").mkdir()
        shutil.copy2(
            ROOT / "scripts/deployment_data.py", restored_root / "scripts/deployment_data.py"
        )
        restored = Deployment(
            restored_root,
            overlay=ROOT / "tests/installation/compose.mock.yaml",
            project="scientific-ragagent-restore-test",
        )
        stage("restore_into_independent_empty_project")
        restored.restore(backup, confirm_empty=True)
        restored.start(build=False)
        assert request("/api/papers/" + pid + "/pdf") == original
        restored_providers = request("/api/providers")["agents"]
        assert all(not value["key_configured"] for value in restored_providers.values())
        assert {
            role: {k: v for k, v in value.items() if k != "key_configured"}
            for role, value in restored_providers.items()
        } == {
            role: {k: v for k, v in value.items() if k != "key_configured"}
            for role, value in providers["agents"].items()
        }
        for rid in runs:
            assert request("/api/runs/" + rid)["status"] == "completed"
        restored.stop(uninstall=True)
        deployment.start(build=False)
        assert request("/api/papers/" + pid + "/pdf") == original
        assert (backup / "backup-manifest.json").exists()
    stage("all_automatic_engineering_checks_passed")
    print(
        "PASS: real native-PDF upload/index, MOCK RAG/Research and four ex"
        "ports, all-worker/DB failure recovery, backup, restart/migration/"
        "config/history, uninstall/reinstall volume preservation. Scientif"
        "ic quality NOT MEASURED."
    )


if __name__ == "__main__":
    main()
