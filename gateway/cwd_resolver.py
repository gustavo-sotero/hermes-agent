"""Compose the per-session working-directory resolver for the messaging gateway.

Messaging sessions (Telegram, WhatsApp, …) historically persisted ``cwd =
NULL`` in ``state.db`` because the gateway never resolved one at row
creation. Without a cwd, ``tui_gateway/project_tree.build_tree`` cannot place
the session under any project and it buckets into the synthetic
``__no_project__`` ("Home") project.

This module builds the ``cwd_resolver`` the session store calls with
``(session_key, source)``. Precedence (most specific first):

1. the per-session working-directory record (``terminal_tool``), written by
   surfaces/plugins that actually anchor a conversation to a folder — e.g.
   the ``project-switcher`` plugin's ``/project use`` (``record_session_cwd``);
2. the active project's primary path (``projects.db`` ``active_id``), the
   configured intent for messaging sessions that never got an explicit
   workspace;
3. the resolved ``TERMINAL_CWD`` (from ``config.yaml terminal.cwd`` /
   ``MESSAGING_CWD``) — used only when it is a real directory.

Junk roots (the bare home directory and the Hermes home tree) are never
returned: stamping them would put sessions straight back into the "Home"
bucket, since ``project_tree`` filters those roots as junk. When nothing
resolves, ``None`` is returned and the row stays NULL (previous behavior).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _is_junk_root(path: str, hermes_home: str) -> bool:
    """True when *path* must never be stamped as a session cwd.

    Mirrors ``project_tree``'s junk-root policy (the bare home dir and the
    Hermes state tree are filtered there), so stamping these would be
    pointless — the session would land right back in the "Home" bucket.

    Two containment directions are junk:
      - the candidate IS the Hermes home or a descendant of it (stamping the
        state tree would put sessions straight back into Home);
      - the candidate CONTAINS the Hermes home — i.e. it is the user's home
        dir or a broad ancestor (``TERMINAL_CWD`` commonly resolves to the
        bare home), which project_tree also treats as junk.
    """
    try:
        resolved = str(Path(path).resolve())
    except Exception:
        return True
    home = str(Path(hermes_home or "").resolve())
    if not home:
        return False
    try:
        rel = os.path.relpath(resolved, home)
    except ValueError:
        return False
    candidate_inside_home = rel == "." or not rel.startswith("..")
    home_inside_candidate = (
        os.path.relpath(home, resolved) == "."
        or not os.path.relpath(home, resolved).startswith("..")
    )
    # resolved == home, resolved inside home, or home inside resolved.
    return candidate_inside_home or home_inside_candidate


def _valid_cwd(path: Optional[str], hermes_home: str) -> Optional[str]:
    """Return *path* when it is a usable, existing, non-junk directory."""
    if not path or not isinstance(path, str):
        return None
    stripped = path.strip()
    if not stripped:
        return None
    try:
        expanded = os.path.abspath(os.path.expanduser(stripped))
    except Exception:
        return None
    if not os.path.isdir(expanded):
        return None
    if _is_junk_root(expanded, hermes_home):
        logger.debug(
            "gateway cwd candidate %r is a junk root (home/Hermes home); "
            "refusing to stamp it",
            expanded,
        )
        return None
    return expanded


def build_gateway_cwd_resolver(
    *,
    terminal_cwd: str,
    hermes_home: str,
    projects_db_path: str,
    get_session_cwd: Callable[[Optional[str]], Optional[str]],
    get_active_project_path: Callable[[], Optional[str]],
) -> Callable[[Optional[str], Any], Optional[str]]:
    """Build the session cwd resolver.

    Args:
        terminal_cwd: the resolved ``TERMINAL_CWD`` (may be a placeholder
            string or empty).
        hermes_home: the profile's Hermes home (junk-filter anchor).
        projects_db_path: path of the per-profile ``projects.db``.
        get_session_cwd: read the per-session cwd record
            (``terminal_tool.get_session_cwd`` semantics).
        get_active_project_path: resolve the active project's primary path
            (``projects_db`` ``active_id`` → project primary path). Called on
            every resolution so a ``/project use`` switch takes effect on the
            next session creation/refresh.
    """

    def resolve(session_key: Optional[str], _source: Any) -> Optional[str]:
        # 1) The session's own recorded workspace (most specific): set by
        #    surfaces/plugins that explicitly anchor the conversation.
        try:
            recorded = get_session_cwd(session_key)
        except Exception as exc:
            logger.debug("gateway cwd resolver: session-record read failed: %s", exc)
            recorded = None
        resolved = _valid_cwd(recorded, hermes_home)
        if resolved:
            return resolved

        # 2) The active project's primary path: the configured intent for a
        #    messaging session with no explicit workspace.
        try:
            active = get_active_project_path()
        except Exception as exc:
            logger.debug("gateway cwd resolver: active-project read failed: %s", exc)
            active = None
        resolved = _valid_cwd(active, hermes_home)
        if resolved:
            return resolved

        # 3) The resolved terminal cwd — only when it is a real, non-junk dir.
        resolved = _valid_cwd(terminal_cwd, hermes_home)
        return resolved

    return resolve
