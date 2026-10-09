"""Allowlisted, checksum-checked unlink using directory descriptors and no symlinks."""

import hashlib
import os
import stat
from pathlib import Path
from uuid import UUID

from ragagent.domain.deletion import CleanupFile
from ragagent.errors import ApplicationError


def digest_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def manifest_file(root: Path, path: Path, role: str, *, checksum: str | None = None) -> CleanupFile:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError:
        return CleanupFile.model_validate(
            {"role": role, "relative_path": None, "retained_reason": "unmanaged_path"}
        )
    item = CleanupFile.model_validate(
        {"role": role, "relative_path": relative.as_posix(), "sha256": checksum}
    )
    try:
        allowed_parts(item)
    except ApplicationError:
        item.relative_path = None
        item.retained_reason = "unmanaged_path"
        return item
    # Symlinks are never followed, even when preparing the manifest. Cleanup
    # reports the safe refusal code; an operator can remove/repair the link.
    if (
        checksum is None
        and path.is_file()
        and not any(p.is_symlink() for p in (path, *path.parents))
    ):
        item.sha256 = digest_file(path)
    return item


def allowed_parts(item: CleanupFile) -> tuple[str, ...]:
    if item.relative_path is None:
        raise ApplicationError("cleanup_unmanaged_path")
    relative = Path(item.relative_path)
    parts = relative.parts
    if relative.is_absolute() or ".." in parts:
        raise ApplicationError("cleanup_unsafe_path")
    if item.role in {"pdf", "parsed"}:
        suffix = ".pdf" if item.role == "pdf" else ".parsed.json"
        if len(parts) != 1 or not parts[0].endswith(suffix):
            raise ApplicationError("cleanup_unsafe_path")
    else:
        if (
            len(parts) != 3
            or parts[0] != "evaluations"
            or parts[2] not in {"results.json", "results.md", "results.json.tmp", "results.md.tmp"}
        ):
            raise ApplicationError("cleanup_unsafe_path")
        try:
            if str(UUID(parts[1])) != parts[1]:
                raise ValueError
        except ValueError:
            raise ApplicationError("cleanup_unsafe_path") from None
    return parts


def unlink_owned(root: Path, item: CleanupFile) -> None:
    if item.retained_reason is not None:
        return
    parts = allowed_parts(item)
    descriptors = []
    try:
        # Reject symlinks in the configured root's ancestors as well. The root
        # itself and every descending directory are opened with O_NOFOLLOW.
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ApplicationError("cleanup_unsafe_path")
        descriptors.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in parts[:-1]:
            descriptors.append(
                os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptors[-1])
            )
        directory = descriptors[-1]
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ApplicationError("cleanup_unsafe_path")
            if (
                item.sha256 is None
                or hashlib.file_digest(source, "sha256").hexdigest() != item.sha256
            ):
                raise ApplicationError("cleanup_file_changed")
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
                raise ApplicationError("cleanup_file_changed")
            os.unlink(parts[-1], dir_fd=directory)
    except FileNotFoundError:
        return
    except OSError:
        raise ApplicationError("cleanup_file_unavailable") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
