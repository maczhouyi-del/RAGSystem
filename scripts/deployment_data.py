"""Fixed container-side backup operations, no secrets or scientific stdout logs."""

import sys
import tarfile
from pathlib import Path


def main() -> None:
    action = sys.argv[1]
    if action == "health":
        from importlib.metadata import version

        from redis import Redis
        from rq import Worker
        from sqlalchemy import create_engine, text

        from ragagent.queues import queue_name
        from ragagent.settings import Settings

        settings = Settings()
        with create_engine(settings.database_url.get_secret_value()).connect() as connection:
            connection.execute(text("SELECT 1"))
        redis = Redis.from_url(settings.redis_url.get_secret_value())
        if not redis.ping():
            raise SystemExit(1)
        for name in ("interactive", "ingestion", "evaluation"):
            if not any(
                queue_name(name) in worker.queue_names() for worker in Worker.all(connection=redis)
            ):
                raise SystemExit(1)
        version("docling")
        version("sentence-transformers")
    elif action == "guard":
        from sqlalchemy import create_engine, text

        from ragagent.settings import Settings

        with create_engine(Settings().database_url.get_secret_value()).connect() as connection:
            count = connection.scalar(
                text("SELECT count(*) FROM runs WHERE status IN ('queued', 'running')")
            )
            if count:
                raise SystemExit(1)
    elif action == "archive":
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
            for name, root in [("papers", Path("/data")), ("config", Path("/app/config"))]:
                for path in sorted(root.rglob("*")):
                    if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                        raise SystemExit(1)
                    archive.add(
                        path, arcname=str(Path(name) / path.relative_to(root)), recursive=False
                    )
    elif action == "restore":
        roots = {"papers": Path("/data"), "config": Path("/app/config")}
        with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
            for member in archive:
                parts = Path(member.name).parts
                if (
                    not parts
                    or parts[0] not in roots
                    or ".." in parts
                    or Path(member.name).is_absolute()
                    or not (member.isfile() or member.isdir())
                ):
                    raise SystemExit(1)
                target = roots[parts[0]].joinpath(*parts[1:])
                if not target.resolve().is_relative_to(roots[parts[0]]) or target.is_symlink():
                    raise SystemExit(1)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    assert source is not None
                    with target.open("wb") as output:
                        import shutil

                        shutil.copyfileobj(source, output)
                    target.chmod(0o600)
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
