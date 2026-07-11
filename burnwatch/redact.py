"""Client-side context scrubbing — drop secret-shaped keys before enqueue.

Mirrors the backend denylist in ``burnwatch/backend/app/normalize.py`` so the
no-secrets guarantee holds in-process, not only at ingest.
"""
from __future__ import annotations

from typing import Any

# Keep in sync with backend ``_CONTEXT_DENYLIST``.
_CONTEXT_DENYLIST = frozenset(
    {
        "private_key",
        "privatekey",
        "mnemonic",
        "seed",
        "seed_phrase",
        "secret",
        "signature",
        "signed_payload",
        "authorization",
    }
)


def dangerous_context_keys(context: dict[str, Any] | None) -> list[str]:
    """Return context keys that would be stripped (case-insensitive denylist match)."""
    if not context:
        return []
    return sorted(k for k in context if k.lower() in _CONTEXT_DENYLIST)


def scrub_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop denylisted and ``_bw*`` keys; return ``None`` if nothing remains.

    Matching is case-insensitive for denylist entries. Nested dicts are not walked —
    same contract as backend ingest scrubbing.
    """
    if not context:
        return None
    clean = {
        k: v
        for k, v in context.items()
        if k.lower() not in _CONTEXT_DENYLIST and not k.startswith("_bw")
    }
    return clean or None
