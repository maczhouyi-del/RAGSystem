"""Independently hash downloaded CI installers and deployment ZIPs; no execution."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

PLATFORMS = {
    "windows-x86_64": {".msi", ".exe"},
    "macos-aarch64": {".dmg"},
    "macos-x86_64": {".dmg"},
    "linux-x86_64": {".deb", ".AppImage"},
}


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(directory, source):
    if not re.fullmatch("[0-9a-f]{40}", source):
        raise ValueError("source_sha_invalid")
    reports = []
    seen = set()
    for manifest_path in sorted(directory.rglob("installer-manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        platform = manifest["platform"]
        if (
            platform not in PLATFORMS
            or platform in seen
            or manifest["source_commit"] != source
            or manifest["version"] != "0.2.0"
        ):
            raise ValueError("native_manifest_identity_mismatch")
        seen.add(platform)
        native = []
        for item in manifest["artifacts"]:
            relative = Path(item["path"].replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("artifact_path_invalid")
            path = manifest_path.parent / "bundle" / relative
            if (
                path.is_symlink()
                or not path.is_file()
                or checksum(path) != item["sha256"]
                or path.stat().st_size != item["bytes"]
            ):
                raise ValueError("native_artifact_hash_mismatch")
            native.append({**item, "independently_verified": True})
        if {Path(item["path"]).suffix for item in native} != PLATFORMS[platform]:
            raise ValueError("native_bundles_incomplete")
        # Download-action nests each whole artifact under its original name.
        artifact_root = manifest_path.parents[4]
        bundles = list(artifact_root.rglob("RAGSystem-deployment-" + platform + ".zip"))
        if len(bundles) != 1:
            raise ValueError("deployment_zip_required")
        deployment = bundles[0]
        expected = deployment.with_suffix(".zip.sha256").read_text().split()[0]
        if checksum(deployment) != expected:
            raise ValueError("deployment_archive_hash_mismatch")
        with zipfile.ZipFile(deployment) as archive:
            identity = json.loads(archive.read("RAGSystem/deployment-manifest.json"))
            if (
                identity["source_commit"] != source
                or identity["platform"] != platform
                or identity["version"] != "0.2.0"
            ):
                raise ValueError("deployment_identity_mismatch")
            members = set(archive.namelist())
            if members != {"RAGSystem/" + name for name in identity["files"]} | {
                "RAGSystem/deployment-manifest.json"
            }:
                raise ValueError("unmanifested_deployment_member")
            for name, digest in identity["files"].items():
                relative = Path(name)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or name.startswith("tests/")
                    or ".git" in relative.parts
                    or (relative.name.startswith(".env") and relative.name != ".env.example")
                    or relative.name.startswith(".runtime-secrets")
                ):
                    raise ValueError("private_or_test_file_in_deployment")
                if hashlib.sha256(archive.read("RAGSystem/" + name)).hexdigest() != digest:
                    raise ValueError("deployment_member_hash_mismatch")
            if not identity["docker_required"] or identity["scientific_quality"] != "NOT MEASURED":
                raise ValueError("deployment_truth_boundary_invalid")
        reports.append(
            {
                "platform": platform,
                "version": "0.2.0",
                "source_commit": source,
                "native": native,
                "deployment": {
                    "file": deployment.name,
                    "sha256": expected,
                    "bytes": deployment.stat().st_size,
                    "independently_verified": True,
                },
            }
        )
    if seen != set(PLATFORMS):
        raise ValueError("all_four_platform_artifacts_required")
    return {
        "verification": "PASS",
        "environment": "Independent GitHub Actions download; no cross-platform installer execution",
        "source_commit": source,
        "platforms": reports,
        "human_installation": "NOT EXECUTED",
        "scientific_quality": "NOT MEASURED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.directory, args.source)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
