"""Hash actual installer files; an absent Windows bundle fails CI."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--platform",
        default="windows-x86_64",
        choices=["windows-x86_64", "linux-x86_64", "macos-aarch64", "macos-x86_64"],
    )
    args = parser.parse_args()
    required = {
        "windows-x86_64": {".msi", ".exe"},
        "linux-x86_64": {".deb", ".AppImage"},
        "macos-aarch64": {".dmg"},
        "macos-x86_64": {".dmg"},
    }[args.platform]
    artifacts = sorted(
        path for path in args.bundle.rglob("*") if path.is_file() and path.suffix in required
    )
    if not required.issubset({path.suffix for path in artifacts}):
        parser.error("required_native_artifacts_missing")
    desktop = json.loads(Path("frontend/src-tauri/tauri.conf.json").read_text())
    metadata = json.loads(args.metadata.read_text())
    manifest = {
        **metadata,
        "version": desktop["version"],
        "platform": args.platform,
        "signing": "unsigned",
        "artifacts": [
            {
                "path": str(path.relative_to(args.bundle)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in artifacts
        ],
    }
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(
                f"\nVersion {manifest['version']} · {manifest['platform']} · "
                f"Build `{manifest['source_commit']}` · unsigned\n\n"
            )
            summary.write("| Artifact | Bytes | SHA256 |\n| --- | --- | --- |\n")
            for artifact in manifest["artifacts"]:
                summary.write(
                    f"| {artifact['path']} | {artifact['bytes']} | `{artifact['sha256']}` |\n"
                )


if __name__ == "__main__":
    main()
