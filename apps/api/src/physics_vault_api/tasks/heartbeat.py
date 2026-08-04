from __future__ import annotations

import json
import logging
import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import uuid4

from dramatiq import Middleware

from ..config import TaskQueueSettings


logger = logging.getLogger(__name__)


class WorkerHeartbeatMiddleware(Middleware):
    """Publish an expiring Redis heartbeat and recover abandoned SQLite work."""

    def __init__(
        self,
        settings: TaskQueueSettings,
        recovery: Callable[[], object] | None = None,
    ) -> None:
        self.settings = settings
        self._recovery = recovery or _recover_stale_tasks
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def heartbeat_key(self) -> str:
        return f"{self.settings.namespace}:worker-heartbeat:{self._worker_id}"

    def after_process_boot(self, broker) -> None:  # noqa: ANN001
        try:
            self._recovery()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to recover stale background tasks during worker startup")
        self._publish(broker)
        self._thread = Thread(
            target=self._run,
            args=(broker,),
            name="physics-vault-worker-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def after_worker_shutdown(self, broker, worker) -> None:  # noqa: ANN001
        self.stop()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self, broker) -> None:  # noqa: ANN001
        interval = self.settings.worker_heartbeat_interval_seconds
        while not self._stop.wait(interval):
            self._publish(broker)

    def _publish(self, broker) -> None:  # noqa: ANN001
        payload = json.dumps(
            {
                "worker_id": self._worker_id,
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "heartbeat_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
        )
        try:
            broker.client.set(
                self.heartbeat_key,
                payload,
                ex=self.settings.worker_heartbeat_ttl_seconds,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to publish worker heartbeat", exc_info=True)


def _recover_stale_tasks() -> object:
    from ..application import WorkerContainer

    return WorkerContainer.build(recover_stale=True)


__all__ = ["WorkerHeartbeatMiddleware"]
