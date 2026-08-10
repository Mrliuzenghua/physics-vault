"""Coalesced background refresh for embeddings invalidated by question edits."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from pathlib import Path

from ..paths import default_db_path
from ..schemas.embedding_builds import EmbeddingBuildRequest
from .embedding_builds import EmbeddingBuildService
from .embedding_runtime import resolve_dashscope_api_key

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return os.getenv("PHYSICS_VAULT_EMBEDDING_AUTO_REFRESH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class _EmbeddingRefreshCoordinator:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def schedule(self, question_ids: list[str]) -> None:
        for question_id in question_ids:
            self._queue.put(question_id)
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._run,
                    name="question-embedding-refresh",
                    daemon=True,
                )
                self._worker.start()

    def _run(self) -> None:
        while True:
            try:
                first = self._queue.get(timeout=2)
            except queue.Empty:
                return

            question_ids = {first}
            time.sleep(0.5)
            while len(question_ids) < 100:
                try:
                    question_ids.add(self._queue.get_nowait())
                except queue.Empty:
                    break

            ordered_ids = sorted(question_ids)
            try:
                EmbeddingBuildService().build(
                    EmbeddingBuildRequest(
                        question_ids=ordered_ids,
                        dimensions=int(os.getenv("PHYSICS_VAULT_EMBEDDING_DIMENSIONS", "1024")),
                        batch_size=10,
                        concurrency=1,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Automatic embedding refresh failed for %d question(s): %s",
                    len(ordered_ids),
                    exc,
                )
                timer = threading.Timer(60, self.schedule, args=(ordered_ids,))
                timer.daemon = True
                timer.start()


_COORDINATOR = _EmbeddingRefreshCoordinator()


def schedule_question_embedding_refresh(
    question_ids: list[str],
    *,
    db_path: str | Path,
) -> bool:
    """Schedule refresh only for the configured canonical database."""
    clean_ids = list(
        dict.fromkeys(str(item or "").strip() for item in question_ids if str(item or "").strip())
    )
    if not clean_ids or not _enabled() or not resolve_dashscope_api_key():
        return False
    if Path(db_path).resolve() != default_db_path().resolve():
        return False
    _COORDINATOR.schedule(clean_ids)
    return True
