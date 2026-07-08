"""Safe pipeline lock acquisition and release helpers."""

from __future__ import annotations

from contextlib import contextmanager

from backend import persistence as db


class PipelineLockError(RuntimeError):
    pass


def acquire_pipeline_lock_or_raise(novel_id: str) -> None:
    if not db.acquire_pipeline_lock(novel_id):
        lock_info = db.get_pipeline_lock_status(novel_id)
        raise PipelineLockError(f"此小說的流水線正在執行中，請等待完成。{lock_info or ''}".strip())


@contextmanager
def pipeline_lock(novel_id: str):
    acquire_pipeline_lock_or_raise(novel_id)
    try:
        yield
    finally:
        db.release_pipeline_lock(novel_id)

