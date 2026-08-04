from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from ..config import TaskQueueSettings
from .heartbeat import WorkerHeartbeatMiddleware


settings = TaskQueueSettings.from_env()
broker = RedisBroker(
    url=settings.broker_url,
    namespace=settings.namespace,
    socket_connect_timeout=settings.redis_timeout_seconds,
    socket_timeout=settings.redis_timeout_seconds,
)
broker.add_middleware(WorkerHeartbeatMiddleware(settings))
dramatiq.set_broker(broker)
