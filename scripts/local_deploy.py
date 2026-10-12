"""Local installation assistant. Stdlib only; packaged as a native executable.

No provider requests, shell interpolation, Docker output or secret arguments.
Never removes volumes. Use only with a trusted deployment bundle.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

PROJECT = "scientific-ragagent"
WRITERS = ["api", "worker-interactive", "worker-ingestion", "worker-evaluation", "frontend"]
VOLUMES = ["postgres", "redis", "papers", "models", "config"]
KEY_NAMES = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "EMBEDDING_API_KEY"}
# Only known nonsecret runtime settings may enter backups/restores; custom envs can be keys.
BACKUP_SETTINGS = {
    "WEB_AUTH_TOKEN_HASH",
    "LOCAL_AUTH_TOKEN_HASH",
    "PDF_PARSER_MODE",
    "SUPERVISOR_MODEL",
    "RETRIEVER_MODEL",
    "ANALYSIS_MODEL",
    "REVIEWER_MODEL",
    "EMBEDDING_BACKEND",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_REVISION",
    "EMBEDDING_API_KEY_ENV",
    "RERANKER_BACKEND",
    "RERANKER_MODEL",
    "RERANKER_REVISION",
    "CHUNK_TARGET_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "CANDIDATE_TOP_N",
    "EVIDENCE_TOP_K",
    "RRF_K",
    "MINIMUM_RERANK_SCORE",
    "MAX_RETRIEVAL_RETRIES",
    "MAX_REVISIONS",
    "MAX_ITERATIONS",
    "RAG_EVIDENCE_BUDGET",
    "RESEARCH_EVIDENCE_BUDGET",
    "EVALUATION_TIMEOUT_SECONDS",
    "INTERACTIVE_QUEUE",
    "INGESTION_QUEUE",
    "EVALUATION_QUEUE",
    "CONVERSATION_RECENT_MESSAGE_LIMIT",
    "CONVERSATION_CONTEXT_TOKEN_BUDGET",
    "CONVERSATION_SUMMARY_MAX_BYTES",
    "CONVERSATION_MESSAGE_MAX_BYTES",
    "CONVERSATION_RECENT_TOKENS",
    "CONVERSATION_SUMMARY_TOKENS",
    "CONVERSATION_MEMORY_TOKENS",
    "CONVERSATION_MEMORY_TOP_K",
}
ADVICE = {
    "docker_missing": "Install Docker Desktop (Windows/macOS) or Engine + Compose v2 (Linux).",
    "docker_not_running": "Start Docker; Windows must use Linux containers. Then retry.",
    "compose_too_old": "Update Docker Compose to version 2.24 or newer.",
    "port_conflict": (
        "Ports 8000/8080 belong to another service. Resolve it yourself; no process was killed."
    ),
    "pairing_required": (
        "Open Desktop > Connection authorization and paste its nonsecret SHA256 hash."
    ),
    "deployment_failed": (
        "Check Docker Desktop service status, disk/network, and installati"
        "on troubleshooting. Data is retained."
    ),
    "not_ready": (
        "Database/Redis/one of the three workers is not ready. Use Check and then Start to recover."
    ),
    "active_jobs": (
        "Wait for queued/running imports, questions and evaluations to fin"
        "ish before backup/upgrade."
    ),
    "backup_failed": "Backup did not complete. Existing data was retained; do not upgrade.",
    "restore_requires_empty": (
        "Restore is allowed only before this project has any Docker volume"
        "s. Never erase existing data to bypass this check."
    ),
    "backup_invalid": "Backup is incomplete, corrupt or incompatible. Restore was not started.",
    "secret_permissions": (
        "Private file permissions could not be enforced. Configure secrets"
        " securely before continuing."
    ),
}
ADVICE.update(
    {
        "docker_linux_containers_required": (
            "请在 Docker Desktop 切换到 Linux containers，然后重新检查。"
        ),
        "docker_missing": (
            "未找到 Docker。安装 Docker Desktop，完成安装并重启电脑后，重新打开助手检查。"
        ),
        "docker_not_running": (
            "Docker 尚未就绪。打开 Docker Desktop，等待"
            "显示运行中，并切换到 Linux containers，然后重试"
            "。"
        ),
        "wsl_not_ready": (
            "Windows 的 WSL2 尚未就绪。打开 Docker De"
            "sktop 的故障排查，按提示启用 WSL2/虚拟化并重启电脑；"
            "然后重新检查。可用的 Hyper-V 部署无需改用 WSL。"
        ),
        "compose_too_old": (
            "Docker Compose 版本过旧或不可用。更新 Docke"
            "r Desktop（Linux 更新 Compose 至 2.2"
            "4+），然后重试。"
        ),
        "disk_space_low": (
            "部署目录所在磁盘可用空间不足 5 GiB。请选择空间充足的目录；"
            "建议至少 20 GiB，论文和模型还需额外空间。不要删除论文或 "
            "Docker 数据卷来腾空间。"
        ),
        "port_conflict": (
            "本机 8000 或 8080 端口被其他程序占用。先关闭你确认可"
            "以停止的其他应用，再重新检查；助手不会强行结束进程。"
        ),
        "pairing_required": (
            "打开桌面程序的连接授权，复制配对哈希并粘贴到助手。这里不能填写 API Key。"
        ),
        "not_ready": (
            "系统尚未就绪。请点击启动/恢复系统；仍失败时检查 Docker "
            "Desktop 中的服务状态。已有论文、历史和配置会保留。"
        ),
        "deployment_failed": (
            "启动未完成。检查 Docker 的网络访问、可用空间及服务状态后"
            "重试。首次构建可能需要 10–30 分钟；已有数据保留，勿清理 "
            "volumes。"
        ),
        "configuration_invalid": (
            "配置格式无效。检查配对哈希或密钥输入，不能包含换行；原配置不会因此清空。"
        ),
        "secret_permissions": (
            "无法限制私有文件权限。将部署 ZIP 解压到你自己的本机可写目录，避免共享目录，然后重试。"
        ),
        "gui_unavailable": (
            "此环境没有可用的图形界面。请使用 RAGSystem-Setup"
            " --console 或原有命令行操作；数据未修改。"
        ),
    }
)


class DeployError(Exception):
    """Only fixed codes reach the user; subprocess/environment values never do."""


def secure_file(path: Path) -> None:
    if path.is_symlink():
        raise DeployError("secret_permissions")
    if os.name == "nt":
        sid = (
            subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True
            )
            .stdout.decode()
            .strip()
            .split(",")[-1]
            .strip('"')
        )
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise DeployError("secret_permissions")
        result = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:" + ("(OI)(CI)(F)" if path.is_dir() else "(F)"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode:
            raise DeployError("secret_permissions")
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def private_write(path: Path, content: str) -> None:
    if path.is_symlink():
        raise DeployError("secret_permissions")
    temporary = path.with_name(path.name + ".new-" + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            # Enforce the Windows ACL before writing a single secret byte.
            secure_file(temporary)
        except Exception:
            os.close(fd)
            raise
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update_env(path: Path, name: str, value: str) -> None:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]+", name) or any(c in value for c in "\r\n\x00"):
        raise DeployError("configuration_invalid")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(name + "=")]
    # Single quoted dotenv values avoid $ interpolation. Provider keys cannot contain quotes.
    if "'" in value:
        raise DeployError("configuration_invalid")
    lines.append(f"{name}='{value}'")
    private_write(path, "\n".join(lines) + "\n")


class Deployment:
    def __init__(
        self,
        root: Path,
        *,
        overlay: Path | None = None,
        project: str = PROJECT,
        progress: Callable[[str], None] | None = None,
    ):
        if not re.fullmatch(r"scientific-ragagent(?:-[a-z0-9-]+)?", project):
            raise DeployError("configuration_invalid")
        self.project = project
        self.progress = progress or (lambda message: None)
        self.root = root.resolve()
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(self.root),
            "-f",
            str(self.root / "compose.yaml"),
        ]
        if overlay:
            self.compose += ["-f", str(overlay.resolve())]
        self.env = os.environ.copy()
        metadata = self.root / "deployment-manifest.json"
        if metadata.exists():
            self.env["RAGAGENT_SOURCE_COMMIT"] = json.loads(metadata.read_text())["source_commit"]

    def call(
        self,
        args: list[str],
        *,
        output: Path | None = None,
        input_file: Path | None = None,
        code: str = "deployment_failed",
        timeout: int = 2700,
    ) -> bytes:
        if output:
            private_write(output, "")
        with open(output, "wb") if output else open(os.devnull, "wb") as target:
            with open(input_file, "rb") if input_file else open(os.devnull, "rb") as source:
                try:
                    result = subprocess.run(
                        args,
                        cwd=self.root,
                        env=self.env,
                        stdin=source,
                        stdout=target if output else subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=timeout,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    raise DeployError(code) from None
        if result.returncode:
            raise DeployError(code)
        return result.stdout or b""

    def dc(self, *args: str, **kwargs: object) -> bytes:
        return self.call([*self.compose, *args], **kwargs)  # type: ignore[arg-type]

    def dependencies(self) -> None:
        if platform.system() not in {"Windows", "Darwin", "Linux"}:
            raise DeployError("operating_system_unsupported")
        if not shutil.which("docker"):
            raise DeployError("docker_missing")
        self.progress("正在检查 Docker 是否运行…")
        try:
            container_type = self.call(
                ["docker", "info", "--format", "{{.OSType}}"],
                code="docker_not_running",
                timeout=15,
            ).strip()
        except DeployError:
            if platform.system() == "Windows":
                try:
                    self.call(["wsl", "--status"], code="wsl_not_ready", timeout=15)
                except DeployError:
                    raise DeployError("wsl_not_ready") from None
            raise
        if container_type != b"linux":
            raise DeployError("docker_linux_containers_required")
        self.progress("正在检查 Docker Compose 版本与磁盘空间…")
        version = (
            self.dc("version", "--short", code="compose_too_old", timeout=15)
            .decode()
            .strip()
            .lstrip("v")
        )
        match = re.match(r"(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (2, 24):
            raise DeployError("compose_too_old")
        if shutil.disk_usage(self.root).free < 5 * 1024**3:
            raise DeployError("disk_space_low")

    def configuration_status(self) -> dict[str, object]:
        """Read presence only. Never return hashes, key values or dotenv contents."""
        settings: dict[str, str] = {}
        for name in (".env", ".runtime-secrets.env"):
            path = self.root / name
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    key, separator, value = line.partition("=")
                    if separator:
                        settings[key] = value.strip().strip("'\"")
        return {
            "existing": (self.root / ".env").exists(),
            "paired": bool(
                re.fullmatch(r"[a-f0-9]{64}", settings.get("LOCAL_AUTH_TOKEN_HASH", ""))
            ),
            "keys": {name: bool(settings.get(name)) for name in sorted(KEY_NAMES)},
        }

    def save_key(self, name: str, value: str) -> None:
        if name not in KEY_NAMES or not value.strip():
            raise DeployError("configuration_invalid")
        self.initialize()
        update_env(self.root / ".runtime-secrets.env", name, value.strip())

    def initialize(self) -> None:
        path = self.root / ".env"
        if not path.exists():
            password = secrets.token_hex(24)
            template = (self.root / ".env.example").read_text()
            template = template.replace(
                "POSTGRES_PASSWORD=ragagent", "POSTGRES_PASSWORD=" + password
            )
            template = template.replace("ragagent:ragagent@db", "ragagent:" + password + "@db")
            private_write(path, template)
        secure_file(path)
        runtime = self.root / ".runtime-secrets.env"
        if not runtime.exists():
            private_write(
                runtime, "# Private runtime environment. Never share or export this file.\n"
            )
        secure_file(runtime)

    def pair(self, verifier: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", verifier):
            raise DeployError("pairing_required")
        self.initialize()
        update_env(self.root / ".env", "LOCAL_AUTH_TOKEN_HASH", verifier)

    def pair_web(self, token: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token) or token.startswith("sk-"):
            raise DeployError("web_credential_invalid")
        self.initialize()
        update_env(
            self.root / ".env",
            "WEB_AUTH_TOKEN_HASH",
            hashlib.sha256(token.encode("ascii")).hexdigest(),
        )

    def ports(self) -> None:
        owned: set[int] = set()
        listing = self.dc("ps", "--format", "json", timeout=15).decode().strip()
        records = (
            json.loads(listing)
            if listing.startswith("[")
            else [json.loads(line) for line in listing.splitlines() if line]
        )
        for record in records:
            for publisher in record.get("Publishers") or []:
                if publisher.get("URL") == "127.0.0.1":
                    owned.add(int(publisher["PublishedPort"]))
        for port in (8000, 8080):
            with socket.socket() as handle:
                handle.settimeout(1)
                listening = handle.connect_ex(("127.0.0.1", port)) == 0
                if listening and port not in owned:
                    raise DeployError("port_conflict")
            # Unix reuse avoids a false collision on stopped Docker proxy TIME_WAIT.
            # Windows SO_REUSEADDR can hijack an active listener: never use it.
            if os.name == "nt":
                continue  # Docker itself rejects reserved/non-listening unavailable ports.
            with socket.socket() as handle:
                handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    handle.bind(("127.0.0.1", port))
                except OSError:
                    if port not in owned:
                        raise DeployError("port_conflict") from None

    def ready(self, timeout: int = 180) -> None:
        # No proxy, credentials or redirects for local public readiness.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: object, **kwargs: object) -> None:
                return None

        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        deadline = time.monotonic() + timeout
        while True:
            try:
                with client.open("http://127.0.0.1:8000/api/ready", timeout=3) as response:
                    value = json.loads(response.read(65536))
                containers = self.dc("ps", "--format", "json", timeout=15).decode().strip()
                records = (
                    json.loads(containers)
                    if containers.startswith("[")
                    else [json.loads(line) for line in containers.splitlines() if line]
                )
                required = set(WRITERS + ["db", "redis"])
                running = {r["Service"] for r in records if r.get("State") == "running"}
                if value.get("status") == "ready" and required <= running:
                    self.dc(
                        "exec",
                        "-T",
                        "api",
                        "python",
                        "-c",
                        (self.root / "scripts/deployment_data.py").read_text(),
                        "health",
                        code="not_ready",
                    )
                    with client.open("http://127.0.0.1:8080/api/ready", timeout=3) as web:
                        if json.loads(web.read(65536)).get("status") == "ready":
                            return
            except (OSError, ValueError, DeployError):
                pass
            if time.monotonic() >= deadline:
                raise DeployError("not_ready")
            time.sleep(2)

    def start(self, *, build: bool = True) -> None:
        self.progress("检查安装条件；已有数据与配置会保留。")
        self.dependencies()
        self.initialize()
        text = (self.root / ".env").read_text()
        match = re.search(
            ("^(?:LOCAL_AUTH_TOKEN_HASH|WEB_AUTH_TOKEN_HASH)=['\\\"]?([a-f0-9]{64})['\\\"]?\\s*$"),
            text,
            re.M,
        )
        if not match:
            raise DeployError("pairing_required")
        self.ports()
        self.progress("正在下载/构建并启动系统（首次约 10–30 分钟）。请保持 Docker 运行。")
        print(
            "Starting database, migration, API, three workers and Web. First b"
            "uild can take 10–30 minutes."
        )
        args = ["up", "-d", "--wait", "--wait-timeout", "300"]
        if build:
            args.append("--build")
        else:
            args.append("--no-build")
        self.dc(*args)
        self.progress("正在检查数据库初始化、后台任务与桌面连接…")
        self.ready()
        self.progress("基础服务已就绪。回到桌面连接授权，再配置模型；尚未调用模型测试。")
        print(
            "PASS: local infrastructure ready. Model inference/real scientific"
            " quality NOT MEASURED."
        )

    def stop(self, *, uninstall: bool = False) -> None:
        self.dc("down" if uninstall else "stop", "--timeout", "120")
        print("Stopped. All Docker volumes, local configuration and credentials retained.")

    def backup(self, destination: Path) -> Path:
        self.dc(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            (self.root / "scripts/deployment_data.py").read_text(),
            "guard",
            code="active_jobs",
        )
        destination = destination.resolve()
        if destination.is_relative_to(self.root):
            raise DeployError("backup_directory_must_be_outside_deployment")
        destination.mkdir(parents=True, exist_ok=True)
        folder = destination / (
            "rag-backup-"
            + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + secrets.token_hex(4)
        )
        folder.mkdir(mode=0o700)
        secure_file(folder)
        # Windows backup files receive the same private ACL as secret files.
        completed = False
        try:
            self.dc("stop", "--timeout", "120", *WRITERS)
            self.dc(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "python",
                "migrate",
                "-c",
                (self.root / "scripts/deployment_data.py").read_text(),
                "guard",
                code="active_jobs",
            )
            self.dc(
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "ragagent",
                "-d",
                "ragagent",
                "-Fc",
                output=folder / "database.dump",
                code="backup_failed",
            )
            self.dc(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "python",
                "migrate",
                "-c",
                (self.root / "scripts/deployment_data.py").read_text(),
                "archive",
                output=folder / "data-config.tar",
                code="backup_failed",
            )
            settings = {}
            for line in (self.root / ".env").read_text().splitlines():
                name, separator, value = line.partition("=")
                if separator and name in BACKUP_SETTINGS:
                    settings[name] = value
            private_write(folder / "settings.json", json.dumps(settings, indent=2) + "\n")
            hashes = {}
            for path in folder.iterdir():
                secure_file(path)
                with path.open("rb") as handle:
                    hashes[path.name] = hashlib.file_digest(handle, "sha256").hexdigest()
            private_write(
                folder / "backup-manifest.json",
                json.dumps(
                    {
                        "format": 1,
                        "postgres_major": 17,
                        "project": self.project,
                        "files": hashes,
                        "runtime_secrets": (
                            "EXCLUDED; preserve original private runtime file separately"
                        ),
                        "model_cache": "EXCLUDED; redownload pinned weights",
                    },
                    indent=2,
                )
                + "\n",
            )
            completed = True
        finally:
            # Resume original images only: never migrate/build during backup recovery.
            self.dc("start", *WRITERS)
        if not completed:
            raise DeployError("backup_failed")
        print("PASS: quiesced PostgreSQL/PDF/config backup; credentials and model cache excluded.")
        return folder

    def restore(self, folder: Path, *, confirm_empty: bool) -> None:
        folder = folder.resolve()
        try:
            manifest = json.loads((folder / "backup-manifest.json").read_text())
            if (
                manifest["format"] != 1
                or manifest["postgres_major"] != 17
                or set(manifest["files"]) != {"database.dump", "data-config.tar", "settings.json"}
            ):
                raise ValueError
            for name, digest in manifest["files"].items():
                path = folder / name
                if path.is_symlink():
                    raise ValueError
                with path.open("rb") as handle:
                    if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                        raise ValueError
        except (OSError, ValueError, KeyError):
            raise DeployError("backup_invalid") from None
        if not confirm_empty:
            raise DeployError("restore_requires_empty")
        self.dependencies()
        existing = (
            self.call(["docker", "volume", "ls", "--format", "{{.Name}}"]).decode().splitlines()
        )
        if any(f"{self.project}_{name}" in existing for name in VOLUMES):
            raise DeployError("restore_requires_empty")
        self.initialize()
        self.dc("up", "-d", "--wait", "db", "redis")
        self.dc(
            "exec",
            "-T",
            "db",
            "pg_restore",
            "--exit-on-error",
            "-U",
            "ragagent",
            "-d",
            "ragagent",
            input_file=folder / "database.dump",
        )
        self.dc(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "migrate",
            "-c",
            (self.root / "scripts/deployment_data.py").read_text(),
            "restore",
            input_file=folder / "data-config.tar",
        )
        settings = json.loads((folder / "settings.json").read_text())
        for name, value in settings.items():
            if name in BACKUP_SETTINGS:
                update_env(self.root / ".env", name, str(value).strip("'\""))
        print("Restored into new volumes. Pair this desktop, reconfigure private keys, then Start.")


def wizard(deployment: Deployment) -> None:
    print("RAGSystem 本地部署助手 / Local setup (Docker required; no paid model calls)")
    while True:
        choice = input(
            "1 检查 Check  2 配对并启动 Pair/Start  3 启动 Start  4 停止 Stop  5 API密钥 Se"
            "cret  6 备份 Backup  7 升级 Upgrade  8 卸载容器(保留数据) Uninstall  "
            "9 Web配对  0 Exit\n>"
            " "
        ).strip()
        if choice == "0":
            return
        try:
            if choice == "1":
                deployment.dependencies()
                deployment.ready(timeout=0)
                print("PASS: Docker and all services ready.")
            elif choice == "2":
                deployment.pair(
                    input(
                        "Desktop > Connection authorization 的 SHA256 哈希 (not API key): "
                    ).strip()
                )
                deployment.start()
            elif choice == "3":
                deployment.start()
            elif choice == "4":
                deployment.stop()
            elif choice == "5":
                name = input(
                    "Runtime variable (OPENAI_API_KEY / ANTHROPIC_API_KEY / DEEPSEEK_A"
                    "PI_KEY / EMBEDDING_API_KEY): "
                ).strip()
                if name not in KEY_NAMES:
                    raise DeployError("configuration_invalid")
                deployment.initialize()
                update_env(
                    deployment.root / ".runtime-secrets.env",
                    name,
                    getpass.getpass("API key (hidden; local private runtime file): "),
                )
                print(
                    "Saved privately. Start to recreate services; select provider/mode"
                    "l in Settings. No inference called."
                )
            elif choice == "9":
                deployment.pair_web(
                    getpass.getpass(
                        "Web credential: password-manager random 43–128 URL-safe characters "
                        "(hidden; NOT an API key): "
                    )
                )
                deployment.start()
            elif choice in {"6", "7"}:
                backup = deployment.backup(
                    Path(input("Backup parent folder (outside deployment directory): ").strip())
                )
                print("Backup:", backup)
                if choice == "7":
                    deployment.start()
            elif choice == "8":
                if input("Type KEEP DATA to remove containers only: ") == "KEEP DATA":
                    deployment.stop(uninstall=True)
        except (DeployError, OSError, ValueError, subprocess.SubprocessError) as error:
            code = str(error) if isinstance(error, DeployError) else "deployment_failed"
            print(
                "ERROR:",
                code,
                ADVICE.get(code, "See installation troubleshooting; existing data is retained."),
            )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        choices=[
            "check",
            "start",
            "stop",
            "pair",
            "backup",
            "upgrade",
            "uninstall",
            "restore",
            "identity",
        ],
    )
    parser.add_argument("--directory", type=Path)
    parser.add_argument(
        "--overlay",
        type=Path,
        help="Trusted operator Compose overlay (CI/proxy); ordinary users omit",
    )
    parser.add_argument("--verifier")
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--confirm-empty-restore", action="store_true")
    parser.add_argument("--console", action="store_true", help="Use the original console wizard")
    parser.add_argument(
        "--gui", action="store_true", help="Open graphical setup (Windows supported)"
    )
    parser.add_argument(
        "--gui-smoke",
        action="store_true",
        help="Native CI GUI startup check; no Docker/model calls",
    )
    args = parser.parse_args()
    root = args.directory or (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    deployment = Deployment(root, overlay=args.overlay)
    try:
        if args.action == "identity":
            machine = platform.machine().lower()
            architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
            print(
                json.dumps(
                    {
                        "version": "0.2.0",
                        "platform": {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
                            platform.system(), "unknown"
                        ),
                        "architecture": architecture,
                    }
                )
            )
        elif not args.action:
            if args.gui or args.gui_smoke or (platform.system() == "Windows" and not args.console):
                from setup_gui import launch

                if not launch(deployment, smoke=args.gui_smoke):
                    raise DeployError("gui_unavailable")
            else:
                wizard(deployment)
        elif args.action == "check":
            deployment.dependencies()
            deployment.ready(timeout=0)
            print("PASS: local infrastructure ready; models NOT MEASURED.")
        elif args.action == "pair":
            deployment.pair(args.verifier or "")
        elif args.action == "start":
            deployment.start()
        elif args.action == "stop":
            deployment.stop()
        elif args.action == "uninstall":
            deployment.stop(uninstall=True)
        elif args.action in {"backup", "upgrade"}:
            if not args.backup_directory:
                parser.error("--backup-directory required")
            print(deployment.backup(args.backup_directory))
            if args.action == "upgrade":
                deployment.start()
        elif args.action == "restore":
            if not args.backup_directory:
                parser.error("--backup-directory required")
            deployment.restore(args.backup_directory, confirm_empty=args.confirm_empty_restore)
        return 0
    except (DeployError, OSError, ValueError, subprocess.SubprocessError) as error:
        code = str(error) if isinstance(error, DeployError) else "deployment_failed"
        print(
            "ERROR:",
            code,
            ADVICE.get(code, "See installation troubleshooting; existing data is retained."),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
