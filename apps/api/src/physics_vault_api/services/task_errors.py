from __future__ import annotations

import socket
import zipfile
from dataclasses import dataclass
from urllib.error import HTTPError, URLError


@dataclass(frozen=True, slots=True)
class ClassifiedTaskError:
    error_type: str
    user_message: str
    technical_details: str
    retryable: bool


class RetryableTaskError(RuntimeError):
    """Explicitly marks a task failure as transient."""


class NonRetryableTaskError(RuntimeError):
    """Explicitly marks bad input or another permanent task failure."""


_TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "rate limit",
    "too many requests",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "temporary failure",
    "network",
    "redis",
    "限流",
    "超时",
    "网络",
    "暂时不可用",
)

_PERMANENT_MARKERS = (
    "unsupported",
    "invalid argument",
    "invalid parameter",
    "corrupt",
    "damaged",
    "bad zip",
    "file not found",
    "格式不支持",
    "不支持的格式",
    "文件损坏",
    "参数错误",
)


def classify_task_error(exc: BaseException) -> ClassifiedTaskError:
    details = str(exc) or exc.__class__.__name__
    lowered = details.lower()
    error_type = exc.__class__.__name__

    if isinstance(exc, NonRetryableTaskError):
        return ClassifiedTaskError(error_type, "任务输入无效，无法继续处理", details, False)
    if isinstance(exc, RetryableTaskError):
        return ClassifiedTaskError(error_type, "外部服务暂时不可用，系统将自动重试", details, True)

    if isinstance(exc, HTTPError):
        retryable = exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
        message = "模型服务暂时不可用，系统将自动重试" if retryable else "模型服务拒绝了任务请求"
        return ClassifiedTaskError(error_type, message, details, retryable)

    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout, URLError)):
        return ClassifiedTaskError(error_type, "网络连接暂时异常，系统将自动重试", details, True)

    try:
        from redis.exceptions import RedisError

        if isinstance(exc, RedisError):
            return ClassifiedTaskError(error_type, "任务队列暂时不可用，系统将自动重试", details, True)
    except ImportError:
        pass

    if isinstance(exc, (ValueError, TypeError, FileNotFoundError, PermissionError, zipfile.BadZipFile, UnicodeError)):
        return ClassifiedTaskError(error_type, "输入文件或参数无效，请检查后重试", details, False)
    if any(marker in lowered for marker in _PERMANENT_MARKERS):
        return ClassifiedTaskError(error_type, "输入文件或参数无效，请检查后重试", details, False)
    if any(marker in lowered for marker in _TRANSIENT_MARKERS):
        return ClassifiedTaskError(error_type, "外部服务暂时不可用，系统将自动重试", details, True)

    # Unknown worker failures are retried within the configured bound. This is
    # safer for intermittent model/provider failures that arrive wrapped in a
    # generic RuntimeError, while max_retries still prevents infinite loops.
    return ClassifiedTaskError(error_type, "任务执行异常，系统将自动重试", details, True)


def should_retry_task(_retry_count: int, exc: BaseException) -> bool:
    return classify_task_error(exc).retryable


__all__ = [
    "ClassifiedTaskError",
    "NonRetryableTaskError",
    "RetryableTaskError",
    "classify_task_error",
    "should_retry_task",
]
