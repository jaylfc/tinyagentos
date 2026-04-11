"""Retry wrapper for outbound inference HTTP calls.

Every inference path (embed, rerank, chat completions) uses this module so
transient connection errors and 5xx responses are handled uniformly.

Design:
- Exponential backoff: 100ms, 300ms, 900ms, 2700ms, then give up.
- Retries only on connection errors and 5xx responses.
- Never retries on 4xx (client errors are not transient).
- Caller passes a zero-arg factory so the coroutine can be re-created on
  each attempt (httpx coroutines cannot be awaited twice).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable, Tuple, Type

import httpx

logger = logging.getLogger(__name__)

# Defaults mirror the design doc:  100ms * 3^n capped at 3s
DEFAULT_RETRY_ON: Tuple[Type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
DEFAULT_RETRY_ON_STATUS = frozenset({500, 502, 503, 504})


class _StatusError(Exception):
    """Raised internally when a response has a retryable status code."""
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


async def with_retry(
    coro_factory: Callable[[], Awaitable],
    *,
    max_attempts: int = 5,
    base_delay: float = 0.1,
    multiplier: float = 3.0,
    max_delay: float = 3.0,
    retry_on: Tuple[Type[Exception], ...] = DEFAULT_RETRY_ON,
    retry_on_status: frozenset[int] | set[int] = DEFAULT_RETRY_ON_STATUS,
):
    """Run ``coro_factory()`` with exponential-backoff retry.

    Parameters
    ----------
    coro_factory:
        Zero-arg callable that returns a fresh coroutine each time it is
        called.  Must be re-called on every attempt because coroutines
        cannot be awaited more than once.
    max_attempts:
        Total number of attempts including the first.  Default 5 gives
        delays of 100ms, 300ms, 900ms, 2700ms before giving up.
    base_delay:
        Initial delay in seconds.
    multiplier:
        Multiplicative factor applied after each retry.
    max_delay:
        Upper bound on the per-retry delay in seconds.
    retry_on:
        Tuple of exception types that warrant a retry.
    retry_on_status:
        Set of HTTP status codes (from ``httpx.HTTPStatusError``) that
        warrant a retry.  4xx codes are never retried regardless of this
        set.

    Returns
    -------
    Whatever the coroutine returns on success.

    Raises
    ------
    The last exception seen after all attempts are exhausted.
    """
    last_exc: Exception | None = None
    delay = base_delay

    for attempt in range(1, max_attempts + 1):
        try:
            result = await coro_factory()
            # If the caller returns an httpx.Response we check its status.
            # This lets callers wrap e.g. client.post() directly without
            # manually calling raise_for_status() before returning.
            if isinstance(result, httpx.Response):
                if result.status_code in retry_on_status and result.status_code >= 500:
                    raise _StatusError(result.status_code)
            return result
        except _StatusError as exc:
            last_exc = exc
            if attempt < max_attempts:
                logger.warning(
                    "retry: attempt %d/%d failed with status %d, retrying in %.1fs",
                    attempt, max_attempts, exc.status_code, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * multiplier, max_delay)
        except httpx.HTTPStatusError as exc:
            # Only retry on server errors (5xx), never on client errors (4xx).
            if exc.response.status_code in retry_on_status and exc.response.status_code >= 500:
                last_exc = exc
                if attempt < max_attempts:
                    logger.warning(
                        "retry: attempt %d/%d failed with HTTP %d, retrying in %.1fs",
                        attempt, max_attempts, exc.response.status_code, delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * multiplier, max_delay)
            else:
                # 4xx or unexpected: do not retry, propagate immediately.
                raise
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt < max_attempts:
                logger.warning(
                    "retry: attempt %d/%d failed with %s, retrying in %.1fs",
                    attempt, max_attempts, type(exc).__name__, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * multiplier, max_delay)
            else:
                break

    logger.error(
        "retry: all %d attempts exhausted, last error: %s",
        max_attempts, last_exc,
    )
    raise last_exc  # type: ignore[misc]
