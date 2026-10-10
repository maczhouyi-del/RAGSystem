"""Read-only, standard-library environment diagnostics; no implicit model requests."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def command_available(arguments: list[str]) -> bool:
    try:
        return (
            subprocess.run(
                arguments,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
                cwd=ROOT,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def port_state(port: int) -> str:
    with socket.socket() as probe:
        try:
            # Binding (rather than connect) also detects non-listening reservations.
            if sys.platform == "win32":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("127.0.0.1", port))
            return "free"
        except OSError:
            return "occupied"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(port: int, path: str, *, token: str = "", body: dict | None = None) -> dict:
    headers = {"Authorization": "Bearer " + token} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
    # Credentials stay on loopback, including when a foreign service redirects.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=20 if body is not None else 3) as response:
            result = json.loads(response.read(1_000_000))
            return result if isinstance(result, dict) else {}
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def diagnose(port: int = 8000, web_port: int = 8080, *, test_model: bool = False) -> dict:
    checks = []

    def add(code: str, state: str, advice: str) -> None:
        checks.append({"code": code, "state": state, "advice": advice})

    add("python", "available", "诊断脚本使用 Python 3.11+，无需安装项目依赖。")
    docker = shutil.which("docker")
    add(
        "docker",
        "available" if docker else "missing",
        "Docker 部署需安装并启动 Docker Desktop / Docker Engine。",
    )
    add(
        "docker_daemon",
        "available" if docker and command_available([docker, "info"]) else "unavailable",
        "若使用 Docker：启动 Docker Desktop；Linux 检查 Docker 服务及当前用户权限。",
    )
    add(
        "compose",
        "available"
        if docker and command_available([docker, "compose", "version"])
        else "unavailable",
        "Docker 部署需安装 Compose v2 插件；用 docker compose version 验证。",
    )
    add(
        "environment_file",
        "present" if (ROOT / ".env").is_file() else "missing",
        "Docker 部署缺 .env 时，按 docs/deployment.md 配置并在桌面端配对；脚本不读写此文件。",
    )
    try:
        free = shutil.disk_usage(ROOT).free
        add(
            "disk",
            "available" if free >= 5 * 1024**3 else "low",
            "项目所在磁盘至少预留 5 GiB；模型与 PDF 会另需更多空间。",
        )
    except OSError:
        add("disk", "unknown", "检查项目目录与磁盘访问权限。")
    add(
        "backend_port",
        port_state(port),
        f"端口 {port}：占用可能是正常后端；若后端不可达，先确认占用进程再关闭或调整部署端口。",
    )
    add(
        "web_port",
        port_state(web_port),
        f"端口 {web_port}：占用可能是正常 Web 服务；冲突时检查占用进程，勿直接终止未知进程。",
    )
    health = request(port, "/api/health")
    backend = health.get("status") == "ok"
    add(
        "backend",
        "available" if backend else "unavailable",
        "在项目目录执行 docker compose up --build；本地开发按 docs/deployment.md 启动后端。",
    )
    auth = request(port, "/api/auth/status") if backend else {}
    initialized = auth.get("initialized")
    add(
        "local_auth",
        "initialized"
        if initialized is True
        else "not_initialized"
        if initialized is False
        else "unknown",
        "打开桌面端 Connection authorization 完成本机配对；保留现有授权与数据库。",
    )
    token = os.environ.get("RAGAGENT_DIAGNOSTIC_TOKEN") or os.environ.get("LOCAL_AUTH_TOKEN", "")
    details = request(port, "/api/diagnostics", token=token) if backend and initialized else {}
    add(
        "diagnostic_access",
        "available" if details.get("build") else "unknown",
        "详细状态需授权：在已授权 UI 查看 Diagnostics，或通过进程环境 "
        "RAGAGENT_DIAGNOSTIC_TOKEN 提供配对凭据；勿粘贴到命令行或报告。",
    )
    for service, advice in (
        ("database", "检查 docker compose ps db 及数据库连接配置；不要重置数据卷。"),
        ("redis", "检查 docker compose ps redis 及 Redis 连接配置。"),
    ):
        state = details.get(service)
        add(service, state if state in ("available", "unavailable") else "unknown", advice)
    queues = details.get("queues")
    for role in ("interactive", "ingestion", "evaluation"):
        selected = queues.get(role) if isinstance(queues, dict) else None
        workers = selected.get("workers") if isinstance(selected, dict) else None
        state = (
            "available"
            if isinstance(workers, int) and workers > 0
            else "unavailable"
            if workers == 0
            else "unknown"
        )
        add(
            "worker_" + role,
            state,
            f"启动对应 worker：docker compose up -d worker-{role}；"
            f"本地使用 python -m ragagent.worker --queue {role}。",
        )
    config = details.get("chat_configuration")
    configured = isinstance(config, dict) and all(
        isinstance(config.get(role), dict) and config[role].get("credential_configured") is True
        for role in ("supervisor", "retriever", "analyst", "reviewer")
    )
    add(
        "models",
        "configured" if configured else "not_configured" if config else "unknown",
        "在 Settings 配置四个角色及运行时凭据；配置成功尚不代表模型可调用。",
    )
    dependencies = details.get("runtime_dependencies", {})
    for name in ("docling", "local_models"):
        state = dependencies.get(name) if isinstance(dependencies, dict) else None
        add(
            name,
            state if state in ("installed", "missing", "not_required") else "unknown",
            "后端缺依赖时重新构建 Docker 镜像；本地开发执行 uv sync --locked --extra parsing "
            "--extra models（会下载依赖，需要额外磁盘）；已安装不等于模型加载或解析成功。",
        )
    inference = "not_tested"
    if test_model and configured:
        tested = request(port, "/api/providers/test", token=token, body={"agent": "supervisor"})
        inference = (
            "succeeded"
            if tested.get("ok") is True and tested.get("agent") == "supervisor"
            else "failed"
        )
    add(
        "inference_supervisor",
        inference,
        "仅 --test-model 显式发起 supervisor 小型真实调用（可能收费）；"
        "成功只证明该角色本次调用，不代表其他模型或科研质量。",
    )
    corpus = details.get("corpus", {})
    state = corpus.get("state") if isinstance(corpus, dict) else None
    add(
        "corpus",
        state if state in ("available", "empty") else "unknown",
        "知识库为空时先上传 PDF 并等待索引；只有 indexed、有 chunk 且未撤回/撤稿的论文计为可用。",
    )
    required = ["backend", "diagnostic_access", "database", "redis"] + [
        "worker_" + role for role in ("interactive", "ingestion", "evaluation")
    ]
    ready = all(check["state"] == "available" for check in checks if check["code"] in required)
    return {"infrastructure": "available" if ready else "needs_attention", "checks": checks}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="RAGSystem 只读环境诊断；不修改配置或数据库。")
    parser.add_argument("--json", action="store_true", help="输出可分享的无凭据 JSON")
    parser.add_argument("--port", type=int, default=8000, help="本机后端端口")
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument(
        "--test-model", action="store_true", help="显式验证 supervisor 真实调用，可能产生费用"
    )
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.port, args.web_port)):
        parser.error("端口须在 1–65535 内")
    report = diagnose(args.port, args.web_port, test_model=args.test_model)
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        for check in report["checks"]:
            print(f"{check['code']}: {check['state']} — {check['advice']}")
    return 0 if report["infrastructure"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
