"""Whitelist deployment inputs; never zip working-directory secrets/user data."""

import argparse
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

from build_metadata import metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assistant", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    identity = metadata()
    if not re.fullmatch("[0-9a-f]{40}", identity["source_commit"]):
        parser.error("actual_build_sha_required")
    files = [
        Path(name)
        for name in [
            "compose.yaml",
            "compose.cloud.yaml",
            ".env.example",
            ".dockerignore",
            "pyproject.toml",
            "uv.lock",
            "alembic.ini",
            "LICENSE",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/index.html",
            "frontend/vite.config.ts",
            "frontend/tsconfig.json",
            "frontend/tsconfig.node.json",
            "frontend/eslint.config.js",
            "scripts/build_metadata.py",
            "scripts/deployment_data.py",
            "scripts/annotation_template.py",
            "scripts/audit_evaluation.py",
        ]
        if Path(name).is_file()
    ]
    for name in [
        "src",
        "migrations",
        "docker",
        "frontend/src",
        "frontend/public",
        "docs/installation",
    ]:
        files.extend(
            path
            for path in Path(name).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    files.append(Path("config/agents.yaml"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(set(files)):
            if path.is_symlink():
                parser.error("symlinks_not_allowed")
            data = path.read_bytes()
            hashes[path.as_posix()] = hashlib.sha256(data).hexdigest()
            bundle.writestr("RAGSystem/" + path.as_posix(), data)
        executable = args.assistant.name
        info = zipfile.ZipInfo("RAGSystem/" + executable)
        info.external_attr = 0o100755 << 16
        data = args.assistant.read_bytes()
        hashes[executable] = hashlib.sha256(data).hexdigest()
        bundle.writestr(info, data)
        manifest = {
            **identity,
            "version": "0.2.0",
            "platform": args.platform,
            "docker_required": True,
            "scientific_quality": "NOT MEASURED",
            "files": hashes,
        }
        bundle.writestr("RAGSystem/deployment-manifest.json", json.dumps(manifest, indent=2) + "\n")
    with args.output.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{digest}  {args.output.name}\n"
    )

    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(f"\nDeployment `{args.platform}` build `{identity['source_commit']}`\n\n")
            summary.write(f"`{args.output.name}` SHA256 `{digest}`\n")


if __name__ == "__main__":
    main()
