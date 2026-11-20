"""Wait for already-started writes/cleanup after their caller was cancelled."""

import asyncio
from typing import TypeVar

T = TypeVar("T")


async def finish_pending_task(pending: asyncio.Future[T]) -> T:
    """Drain a shielded task even if cancellation is requested repeatedly.

    Call only while handling cancellation; the caller must re-raise its original
    CancelledError after any required cleanup. Cancelling an awaiter cannot stop
    a SQL operation already running in a worker thread.
    """
    while not pending.done():
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            continue
    return pending.result()
