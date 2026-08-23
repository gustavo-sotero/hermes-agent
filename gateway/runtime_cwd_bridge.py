"""Bridge the gateway's per-session cwd resolver into the session runtime.

The gateway builds a per-session working-directory resolver at startup
(``gateway.cwd_resolver.build_gateway_cwd_resolver``) whose precedence is:
recorded workspace (``/project use``) -> active project primary path ->
non-junk ``TERMINAL_CWD``. That resolver is used today only to stamp
``sessions.cwd`` for sidebar attribution.

This module exposes the pure helper that reuses the SAME resolver to pin the
runtime working directory of a messaging turn: the value is recorded via
``terminal_tool.record_session_cwd`` (so terminal/file tools resolve there)
and passed to ``set_session_vars(cwd=...)`` (so the prompt's "Current
working directory" and context discovery agree).

Kept in its own module (rather than inside the already-huge ``gateway/run.py``)
so the helper is trivially unit-testable without constructing a
``GatewayRunner``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# A resolver returns Optional[str]: None means "no cwd to pin" (junk root,
# missing dir, unavailable store) and the session falls back to its previous
# behavior (TERMINAL_CWD / process cwd).
SessionCwdResolver = Callable[[Optional[str], Any], Optional[str]]


def resolve_session_runtime_cwd(
    resolver: SessionCwdResolver | None,
    session_key: str | None,
) -> Optional[str]:
    """Return the cwd to pin for this session turn, or ``None``.

    ``resolver`` is the gateway cwd resolver built at startup (or ``None``
    when it is unavailable — e.g. projects.db failed to load). Any resolver
    failure degrades to ``None`` so the message handler never crashes on a
    cwd lookup; the session then behaves exactly as before this bridge.

    The resolver never returns a junk root (the bare home dir and the Hermes
    state tree are filtered by ``_is_junk_root``), so the Home directory can
    never be pinned here.
    """
    if resolver is None:
        return None
    try:
        resolved = resolver(session_key, None)
    except Exception as exc:  # pragma: no cover - defensive, fail-open
        logger.warning(
            "session runtime cwd resolution failed for session_key=%r: %s",
            session_key,
            exc,
        )
        return None
    if resolved:
        logger.debug(
            "session runtime cwd for session_key=%r: %s", session_key, resolved
        )
    else:
        logger.debug(
            "session runtime cwd for session_key=%r: none (fallback to "
            "TERMINAL_CWD/process cwd)",
            session_key,
        )
    return resolved or None
