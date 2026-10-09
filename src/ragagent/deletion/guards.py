"""Short PostgreSQL publication locks, never held for provider calls."""

from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from ragagent.db.models import PaperDeletion
from ragagent.deletion.history import source_ids
from ragagent.errors import ApplicationError

# Fixed application namespace/key, independent of user data and Python hash seeds.
LIFECYCLE_LOCK = 731940061


def lifecycle_lock(session: Session, *, exclusive: bool = False) -> None:
    name = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    with session.no_autoflush:
        session.execute(text(f"SELECT {name}(:key)"), {"key": LIFECYCLE_LOCK})


def guard_sources(session: Session, payload: Any) -> None:
    lifecycle_lock(session)
    ids = source_ids(payload)
    if not (ids.papers or ids.chunks or ids.evidence):
        return
    conditions = []
    if ids.papers:
        conditions.append(PaperDeletion.paper_id.in_(ids.papers))
    if ids.chunks:
        conditions.append(PaperDeletion.chunk_ids.op("?|")(array(sorted(ids.chunks))))
    if ids.evidence:
        conditions.append(PaperDeletion.evidence_ids.op("?|")(array(sorted(ids.evidence))))
    with session.no_autoflush:
        if session.scalar(select(PaperDeletion.paper_id).where(or_(*conditions)).limit(1)):
            raise ApplicationError("source_deleted")
