"""The Burnwatch client: buffer payment metadata and mirror it outbound, async and fail-open."""
from __future__ import annotations

import json
import logging
import threading
import urllib.request
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("burnwatch")

__sdk_version__ = "0.1.2"


class BurnwatchClient:
    """Mirrors agent payments to the Burnwatch backend.

    Design rules: outbound-only, metadata-only, never in the money path. Every
    network operation swallows its errors - a monitoring failure must never break the agent.
    """

    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        flush_interval: float = 2.0,
        max_batch: int = 100,
        timeout: float = 3.0,
        enabled: bool = True,
        max_buffer: int | None = None,
    ) -> None:
        self._url = endpoint.rstrip("/") + "/ingest/payments"
        self._token = token
        self._flush_interval = flush_interval
        self._max_batch = max_batch
        self._timeout = timeout
        self._enabled = enabled
        # Upper bound on buffered events while the backend is unreachable. Failed batches are
        # re-queued (not dropped) until they exceed this, at which point the oldest are evicted.
        self._max_buffer = max_buffer if max_buffer is not None else max(max_batch * 10, 1000)

        self._buf: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if enabled:
            self._thread = threading.Thread(target=self._loop, name="burnwatch-flush", daemon=True)
            self._thread.start()

    # -- public API -----------------------------------------------------------

    def record(
        self,
        *,
        agent_ref: str,
        amount: float,
        recipient: str,
        resource: str | None = None,
        currency: str = "USDC",
        rail: str = "x402",
        status: str = "paid",
        ts: datetime | None = None,
        agent_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Queue one payment for mirroring. Non-blocking; never raises."""
        if not self._enabled:
            return
        event = {
            "agent_ref": agent_ref,
            "amount": amount,
            "recipient": recipient,
            "resource": resource,
            "currency": currency,
            "rail": rail,
            "status": status,
            "ts": (ts or datetime.now(timezone.utc)).isoformat(),
        }
        if agent_name:
            event["agent_name"] = agent_name
        if context:
            event["context"] = context
        with self._lock:
            self._buf.append(event)
            full = len(self._buf) >= self._max_batch
        if full:
            self.flush()

    def flush(self) -> None:
        """Send one batch (up to max_batch) now. Fail-open: on error the batch is re-queued for
        the next flush rather than dropped, so a transient blip does not lose events. The buffer is
        capped (max_buffer) so a sustained outage can never grow it without bound."""
        with self._lock:
            if not self._buf:
                return
            batch, self._buf = self._buf[: self._max_batch], self._buf[self._max_batch :]
        try:
            self._post({"events": batch, "sdk_version": __sdk_version__})
        except Exception as exc:  # noqa: BLE001 - monitoring must never break the caller
            with self._lock:
                # Put the failed batch back ahead of newer events, then keep only the most recent
                # max_buffer so memory is bounded even if the backend stays down.
                self._buf = (batch + self._buf)[-self._max_buffer :]
            log.debug("burnwatch flush failed, re-queued %s events: %s", len(batch), exc)

    def _drain(self) -> None:
        """Flush in batches until the buffer is empty or a send makes no progress (failure)."""
        while True:
            with self._lock:
                n = len(self._buf)
            if n == 0:
                return
            self.flush()
            with self._lock:
                if len(self._buf) >= n:  # send failed or buffer refilled - stop until next tick
                    return

    def close(self) -> None:
        """Stop the background flusher and send anything still buffered (best effort)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._timeout + 1)
        self._drain()

    def __enter__(self) -> "BurnwatchClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- internals ------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.wait(self._flush_interval):
            self._drain()

    def _post(self, payload: dict[str, Any]) -> None:
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            if resp.status >= 400:
                log.debug("burnwatch ingest returned %s", resp.status)


# silence "no handler" warnings while staying quiet by default
log.addHandler(logging.NullHandler())
