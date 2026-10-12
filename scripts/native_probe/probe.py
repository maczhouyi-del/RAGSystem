"""Isolated Windows feasibility probe, not a production runtime or installer.

Real PostgreSQL/pgvector/Garnet/RQ only. Synthetic fixtures, no model calls.
Raw native logs and credentials remain private; only safe reports are artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
GARNET_URL = (
    "https://github.com/microsoft/garnet/releases/download/v2.2.1/win-x64-based-readytorun.zip"
)
GARNET_SHA = "93f0026d305585cd249a91dda6fd44c46bcaa56304115b039f74f23fe630c64a"
PGVECTOR_SOURCE = "cab9da72c04353f143bb06b42ab70a403daac64a"


class ProbeError(Exception):
    """Fixed safe codes, never provider/DB/config values."""


def call(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 90,
    capture: bool = False,
) -> bytes:
    try:
        result = subprocess.run(
            args,
            cwd=REPO,
            env=env,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("native_process_unavailable") from None
    if result.returncode:
        # Executable basename and numeric OS exit only, never args/environment.
        raise ProbeError(f"native_command_failed_{Path(args[0]).stem}_{result.returncode}")
    return result.stdout or b""


def port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def private(path: Path, text: str) -> None:
    from scripts.local_deploy import private_write

    private_write(path, text)


def prepare(root: Path, pg_source: Path, runtime_root: Path) -> None:
    if platform.system() != "Windows" or root.exists() or runtime_root.exists():
        raise ProbeError("isolated_new_windows_workspace_required")
    root.mkdir(parents=True)
    runtime_root.mkdir(parents=True)
    original_version = call([str(pg_source / "bin" / "pg_config.exe"), "--version"], capture=True)
    print("Original PostgreSQL installation executable starts:", original_version.decode().strip())
    # Build only into a copy, never modify the runner's installed PG/service/data.
    for name in ("bin", "lib", "share", "include"):
        shutil.copytree(pg_source / name, root / "postgres" / name)
        shutil.copytree(pg_source / name, runtime_root / "postgres" / name)
    unicode_runtime: dict[str, str] = {"status": "PASS"}
    try:
        call([str(root / "postgres" / "bin" / "pg_config.exe"), "--version"], capture=True)
    except ProbeError as error:
        unicode_runtime = {"status": "FAIL", "safe_error_code": str(error)}
    pg = runtime_root / "postgres" / "bin"
    version = call([str(pg / "pg_config.exe"), "--version"], capture=True).decode().strip()
    if not version.startswith("PostgreSQL 17."):
        raise ProbeError("postgres_major_mismatch")
    archive = root / "garnet.zip"
    with urllib.request.urlopen(GARNET_URL, timeout=120) as response:
        with archive.open("wb") as out:
            shutil.copyfileobj(response, out)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != GARNET_SHA:
        raise ProbeError("runtime_hash_mismatch")
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            relative = Path(member.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts:
                raise ProbeError("runtime_archive_path_invalid")
        z.extractall(runtime_root / "garnet")
    if not (runtime_root / "garnet" / "net8.0" / "GarnetServer.exe").is_file():
        raise ProbeError("runtime_binary_missing")
    (root / "prepared.json").write_text(
        json.dumps(
            {
                "postgres": version,
                "garnet": "2.2.1",
                "garnet_sha256": GARNET_SHA,
                "runtime_root": str(runtime_root),
                "unicode_runtime": unicode_runtime,
            }
        )
    )
    print("Prepared private copied PostgreSQL17 and checksum-verified Garnet2.2.1.")


def resources(root: Path) -> Path:
    return Path(json.loads((root / "prepared.json").read_text())["runtime_root"])


def database(root: Path) -> dict[str, object]:
    import psycopg

    pg = resources(root) / "postgres" / "bin"
    data = root / "pgdata"
    password = secrets.token_urlsafe(32)
    pwfile = root / "pg-password.private"
    private(pwfile, password + "\n")
    selected = port()
    env = os.environ.copy()
    env.update(PGPASSWORD=password, PGHOST="127.0.0.1", PGPORT=str(selected), PGUSER="probe")
    env["PGOPTIONS"] = "-c statement_timeout=30000 -c lock_timeout=10000"
    print("NativeStage: database_initialize")
    call(
        [
            str(pg / "initdb.exe"),
            "-D",
            str(data),
            "-U",
            "probe",
            "--pwfile",
            str(pwfile),
            "--auth-host=scram-sha-256",
            "--auth-local=scram-sha-256",
            "--encoding=UTF8",
            "--locale=C",
        ]
    )
    if not data.is_dir():
        raise ProbeError("postgres_unicode_data_path_not_created")
    start = [
        str(pg / "pg_ctl.exe"),
        "-D",
        str(data),
        "-l",
        str(root / "pg.private.log"),
        "-o",
        f"-h 127.0.0.1 -p {selected}",
        "-w",
        "start",
    ]
    stop = [str(pg / "pg_ctl.exe"), "-D", str(data), "-w", "stop"]
    running = False
    try:
        print("NativeStage: database_start")
        call(start)
        running = True
        call([str(pg / "createdb.exe"), "ragagent_probe"], env=env)
        uri = f"postgresql://probe:{quote(password, safe='')}@127.0.0.1:{selected}/ragagent_probe"
        env.update(
            DATABASE_URL=uri.replace("postgresql:", "postgresql+psycopg:"),
            DATA_DIR=str(root / "papers"),
        )
        print("NativeStage: database_existing_migrations")
        call([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)
        with psycopg.connect(
            uri,
            autocommit=True,
            connect_timeout=10,
            options="-c statement_timeout=30000 -c lock_timeout=10000",
        ) as db:
            extension = db.execute(
                "SELECT extversion FROM pg_extension WHERE extname='vector'"
            ).fetchone()
            if extension != ("0.8.2",):
                raise ProbeError("pgvector_version_mismatch")
            assert db.execute("SELECT version_num FROM alembic_version").fetchone()
            db.execute(
                "CREATE TABLE native_fixture(id int primary key, body text, embedding vector(3))"
            )
            db.execute(
                "INSERT INTO native_fixture VALUES(1,'synthetic native paper','[1,0,0]'),"
                "(2,'unrelated fixture','[0,1,0]')"
            )
            assert db.execute(
                "SELECT id FROM native_fixture ORDER BY embedding <=> '[1,0,0]' LIMIT 1"
            ).fetchone() == (1,)
            assert db.execute(
                "SELECT to_tsvector('english','native paper') @@ plainto_tsquery('english','paper')"
            ).fetchone() == (True,)
            assert db.execute("SELECT similarity('native','native')").fetchone() == (1.0,)
            with (
                psycopg.connect(
                    uri,
                    connect_timeout=10,
                    options="-c statement_timeout=30000 -c lock_timeout=10000",
                ) as first,
                psycopg.connect(
                    uri,
                    connect_timeout=10,
                    options="-c statement_timeout=30000 -c lock_timeout=10000",
                ) as second,
            ):
                first.execute("SELECT id FROM native_fixture WHERE id=1 FOR UPDATE")
                assert (
                    second.execute(
                        "SELECT id FROM native_fixture WHERE id=1 FOR UPDATE SKIP LOCKED"
                    ).fetchall()
                    == []
                )
        dump = root / "backup.private.dump"
        call([str(pg / "pg_dump.exe"), "-Fc", "-f", str(dump), "ragagent_probe"], env=env)
        call([str(pg / "createdb.exe"), "ragagent_restored"], env=env)
        call(
            [str(pg / "pg_restore.exe"), "--exit-on-error", "-d", "ragagent_restored", str(dump)],
            env=env,
        )
        call(stop + ["-m", "immediate"])
        running = False
        call(start)
        running = True
        for name in ("ragagent_probe", "ragagent_restored"):
            with psycopg.connect(
                uri.rsplit("/", 1)[0] + "/" + name,
                connect_timeout=10,
                options="-c statement_timeout=30000 -c lock_timeout=10000",
            ) as db:
                assert db.execute("SELECT count(*) FROM native_fixture").fetchone() == (2,)
        with psycopg.connect(
            uri, connect_timeout=10, options="-c statement_timeout=30000 -c lock_timeout=10000"
        ) as db:
            version = db.execute("SELECT current_setting('server_version')").fetchone()[0]
        hashes = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                pg / "postgres.exe",
                pg / "initdb.exe",
                resources(root) / "postgres" / "lib" / "vector.dll",
            ]
        }
        return {
            "status": "PASS",
            "postgres_version": version,
            "pgvector": "0.8.2",
            "migration": "existing head",
            "checks": [
                "vector",
                "FTS",
                "pg_trgm",
                "SKIP_LOCKED",
                "dump_restore",
                "immediate_stop_recovery",
            ],
            "binary_sha256": hashes,
        }
    finally:
        if running:
            call(stop + ["-m", "fast"])
        pwfile.unlink(missing_ok=True)


def rq_worker() -> int:
    from redis import Redis
    from rq import Queue, Worker

    connection = Redis.from_url(os.environ["NATIVE_PROBE_REDIS_URL"])
    worker = Worker(
        [Queue("native-probe-interactive", connection=connection)], connection=connection
    )
    worker.work(burst=True)
    return 0


def queue(root: Path) -> dict[str, object]:
    from redis import Redis
    from redis.exceptions import AuthenticationError
    from rq import Queue
    from rq.worker import SpawnWorker

    selected = port()
    password = secrets.token_urlsafe(32)
    config = root / "garnet.private.json"
    server = resources(root) / "garnet" / "net8.0" / "GarnetServer.exe"
    private(
        config,
        json.dumps(
            {
                "Port": selected,
                "Address": "127.0.0.1",
                "AuthenticationMode": "Password",
                "Password": password,
                "EnableLua": True,
                "LuaTransactionMode": True,
                "EnableAOF": True,
                "Recover": True,
                "AofCommitFrequencyMs": 0,
                "WaitForCommit": True,
                "LogDir": str(root / "queue-data"),
                "CheckpointDir": str(root / "queue-checkpoints"),
                "LogMemorySize": "64m",
                "PageSize": "1m",
                "IndexMemorySize": "1m",
                "ObjectLogMemorySize": "32m",
                "ObjectLogPageSize": "1m",
                "ObjectLogIndexMemorySize": "1m",
                "AofMemorySize": "32m",
                "AofPageSize": "2m",
                "AofSegmentSize": "32m",
            }
        ),
    )
    client = Redis(host="127.0.0.1", port=selected, password=password, socket_timeout=5)
    native = None
    with (root / "garnet.private.log").open("ab") as logs:

        def start():
            proc = subprocess.Popen(
                [str(server), "--config-import-path", str(config)], stdout=logs, stderr=logs
            )
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if client.ping():
                        return proc
                except Exception:
                    pass
                if proc.poll() is not None:
                    break
                time.sleep(0.25)
            proc.terminate()
            proc.wait(timeout=15)
            logs.flush()
            # Native diagnostic symbols only, never log lines/config values.
            raw = (root / "garnet.private.log").read_text(errors="replace")
            types = sorted(set(re.findall(r"\b[A-Za-z]+Exception\b", raw)))
            symbols = [
                name
                for name in ("lua54", "KeraLua", "hostfxr", "coreclr", "libmsquic")
                if name in raw
            ]
            print(
                "NativeStartupDiagnostics:",
                json.dumps(
                    {
                        "exit_code": proc.returncode,
                        "exception_types": types,
                        "dependency_symbols": symbols,
                    }
                ),
            )
            raise ProbeError("garnet_start_failed")

        try:
            print("NativeStage: queue_authenticated_start")
            native = start()
            try:
                Redis(host="127.0.0.1", port=selected, socket_timeout=3).ping()
            except AuthenticationError:
                pass
            else:
                raise ProbeError("garnet_auth_not_enforced")
            assert (
                client.eval("return redis.call('SET', KEYS[1], ARGV[1])", 1, "native:lua", "yes")
                == b"OK"
            )
            print("NativeStage: queue_BLMOVE")
            client.lpush("native:list", "one")
            assert client.blmove("native:list", "native:moved", 1) == b"one"
            print("NativeStage: queue_WATCH")
            with client.pipeline() as transaction:
                transaction.watch("native:watched")
                transaction.multi()
                transaction.set("native:watched", "yes")
                transaction.execute()
            queues = [
                Queue("native-probe-" + role, connection=client)
                for role in ("interactive", "ingestion", "evaluation")
            ]
            ids = ["native-" + secrets.token_hex(8) for _ in queues]
            print("NativeStage: queue_RQ_enqueue")
            for q, identity in zip(queues, ids, strict=True):
                q.enqueue(
                    "scripts.native_probe.jobs.value", job_id=identity, unique=True, result_ttl=60
                )
                assert q.job_ids == [identity]
            cancelled = queues[0].enqueue(
                "scripts.native_probe.jobs.value", job_id="cancelled-fixture"
            )
            cancelled.cancel()
            assert cancelled.get_status(refresh=True).value == "canceled"
            print("NativeStage: queue_AOF")
            client.execute_command("COMMITAOF")
            native.terminate()
            native.wait(timeout=15)
            native = None
            native = start()
            assert all(q.job_ids == [identity] for q, identity in zip(queues, ids, strict=True))
            print("NativeStage: queue_native_worker")
            environment = os.environ.copy()
            environment["NATIVE_PROBE_REDIS_URL"] = (
                f"redis://:{quote(password, safe='')}@127.0.0.1:{selected}/0"
            )
            with (root / "worker.private.log").open("wb") as worker_log:
                process = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--rq-worker"],
                    env=environment,
                    cwd=REPO,
                    stdout=worker_log,
                    stderr=worker_log,
                )
                try:
                    process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=15)
            job = queues[0].fetch_job(ids[0])
            executed = job is not None and job.get_status(refresh=True).value == "finished"
            raw = (root / "worker.private.log").read_text(errors="replace")
            reason = (
                "OS_FORK_UNAVAILABLE"
                if "has no attribute 'fork'" in raw
                else "native_worker_did_not_finish"
            )
            source = inspect.getsource(SpawnWorker.fork_work_horse)
            return {
                "status": "PASS" if executed else "NO_GO",
                "runtime": "Garnet2.2.1/net8.0 native binary",
                "rq": importlib.metadata.version("rq"),
                "primitive_checks": [
                    "authenticated_loopback",
                    "Lua",
                    "BLMOVE",
                    "WATCH_MULTI_EXEC",
                    "real_RQ_enqueue",
                    "queue_isolation",
                    "queued_cancel",
                    "AOF_restart",
                ],
                "native_worker_execution": executed,
                "reason_code": "none" if executed else reason,
                "windows_capabilities": {
                    name: hasattr(os, name) for name in ("fork", "setpgrp", "wait4")
                },
                "unix_alarm_available": hasattr(signal, "SIGALRM"),
                "spawn_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "spawn_contains_connection_kwargs_in_cli": "redis_kwargs!r" in source,
                "spawn_contains_setpgrp": "os.setpgrp()" in source,
                "spawn_with_password": "NOT EXECUTED: unsafe commandline credential path",
                "three_workers_retry_timeout_stop_recovery": (
                    "NOT EXECUTED: workhorse prerequisite failed"
                    if not executed
                    else "NOT EXECUTED: one synthetic function is insufficient"
                ),
            }
        finally:
            if native is not None and native.poll() is None:
                native.terminate()
                native.wait(timeout=15)
            client.close()
            config.unlink(missing_ok=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--pg-source", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--rq-worker", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.rq_worker:
        return rq_worker()
    if args.workspace is None:
        parser.error("--workspace required")
    if args.prepare:
        if args.pg_source is None or args.runtime_root is None:
            parser.error("--pg-source and --runtime-root required")
        prepare(args.workspace, args.pg_source, args.runtime_root)
        return 0
    if args.output is None:
        parser.error("--output required")
    if platform.system() != "Windows" or not (args.workspace / "prepared.json").is_file():
        raise ProbeError("prepared_windows_workspace_required")
    report = {
        "platform": platform.system(),
        "cpu": platform.machine(),
        "source": os.environ.get("GITHUB_SHA", "local"),
        "fixture": "SYNTHETIC ONLY / NOT A BENCHMARK",
        "pgvector_source": PGVECTOR_SOURCE,
        "garnet_archive_sha256": GARNET_SHA,
        "native_windows11_clean_install": "NOT EXECUTED",
        "models_scientific_quality": "NOT MEASURED",
        "paid_model_calls": 0,
        "production_code_changed": False,
    }
    prepared = json.loads((args.workspace / "prepared.json").read_text())
    report["unicode_runtime_executable"] = prepared["unicode_runtime"]
    try:
        report["database"] = database(args.workspace)
        report["unicode_database_path"] = {"status": "PASS"}
    except Exception as error:
        code = str(error) if isinstance(error, ProbeError) else type(error).__name__
        report["unicode_database_path"] = {"status": "FAIL", "safe_error_code": code}
        # Independent ASCII data fixture measures DB compatibility only. It
        # does not silently turn the failed Unicode scenario into a pass.
        fallback = resources(args.workspace).parent / (
            "rag-native-ascii-data-" + os.environ.get("GITHUB_RUN_ID", secrets.token_hex(8))
        )
        fallback.mkdir()
        (fallback / "prepared.json").write_text(json.dumps(prepared))
        try:
            report["database"] = database(fallback)
        except Exception as error:
            code = str(error) if isinstance(error, ProbeError) else type(error).__name__
            report["database"] = {"status": "FAIL", "safe_error_code": code}
    for name, probe in (("queue", queue),):
        try:
            report[name] = probe(args.workspace)
        except Exception as error:
            code = str(error) if isinstance(error, ProbeError) else type(error).__name__
            report[name] = {"status": "FAIL", "safe_error_code": code}
    go = (
        all(
            report[name]["status"] == "PASS"
            for name in ("database", "queue", "unicode_database_path")
        )
        and report["queue"].get("three_workers_retry_timeout_stop_recovery") == "PASS"
    )
    report["decision"] = "GO_PROTOTYPE_ONLY" if go else "NO_GO_PRODUCTION"
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if go else 2


if __name__ == "__main__":
    raise SystemExit(main())
