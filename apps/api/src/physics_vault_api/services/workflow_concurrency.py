"""Small concurrency helpers for import and AI workflows."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def gather_limited(
    items: Iterable[T],
    limit: int,
    worker: Callable[[T], Awaitable[R]],
) -> list[R]:
    """Run async work with a fixed concurrency limit.

    Results keep the same order as the input items. Exceptions are not hidden;
    callers should catch inside ``worker`` when they need per-item fallback.
    """

    item_list = list(items)
    if not item_list:
        return []

    semaphore = asyncio.Semaphore(max(1, limit))
    results: list[R | None] = [None] * len(item_list)

    async def run_one(index: int, item: T) -> None:
        async with semaphore:
            results[index] = await worker(item)

    await asyncio.gather(*(run_one(index, item) for index, item in enumerate(item_list)))
    return [item for item in results if item is not None]
