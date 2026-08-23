"""Runtime cwd bridge tests: the gateway pins the session working directory.

Covers the pure helper ``resolve_session_runtime_cwd`` (gateway/
runtime_cwd_bridge.py) and the wiring in ``GatewayRunner._set_session_env``
(gateway/run.py), which records the resolved cwd per session and passes it to
``set_session_vars(cwd=...)`` so terminal/file tools and the prompt's
"Current working directory" agree on the project root.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gateway.runtime_cwd_bridge import resolve_session_runtime_cwd


# ---------------------------------------------------------------------------
# resolve_session_runtime_cwd — pure helper
# ---------------------------------------------------------------------------


class TestResolveSessionRuntimeCwd:
    def test_none_resolver_returns_none(self):
        assert resolve_session_runtime_cwd(None, "key-1") is None

    def test_resolver_result_returned(self):
        resolver = lambda key, source: "/some/project"  # noqa: E731
        assert resolve_session_runtime_cwd(resolver, "key-1") == "/some/project"

    def test_resolver_none_result_returns_none(self):
        resolver = lambda key, source: None  # noqa: E731
        assert resolve_session_runtime_cwd(resolver, "key-1") is None

    def test_resolver_empty_string_returns_none(self):
        resolver = lambda key, source: ""  # noqa: E731
        assert resolve_session_runtime_cwd(resolver, "key-1") is None

    def test_resolver_exception_degrades_to_none(self):
        def resolver(session_key, source):
            raise RuntimeError("projects.db locked")

        assert resolve_session_runtime_cwd(resolver, "key-1") is None

    def test_session_key_passed_through(self):
        seen = {}

        def resolver(session_key, source):
            seen["key"] = session_key
            return "/proj"

        resolve_session_runtime_cwd(resolver, "the-session-key")
        assert seen["key"] == "the-session-key"


# ---------------------------------------------------------------------------
# GatewayRunner._set_session_env wiring
# ---------------------------------------------------------------------------


def _make_context(session_key: str = "key-1"):
    from gateway.config import Platform
    from gateway.session import SessionContext, SessionSource

    return SessionContext(
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="123", chat_type="dm"),
        connected_platforms=[Platform.TELEGRAM],
        home_channels={},
        session_key=session_key,
    )


def _make_runner(resolver):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._gateway_cwd_resolver = resolver
    return runner


def _fake_resolver(cwd):
    def resolver(session_key, source):
        return cwd

    return resolver


class TestSetSessionEnvWiring:
    def test_resolves_and_records_cwd_and_passes_to_set_session_vars(self):
        runner = _make_runner(_fake_resolver("/proj/botsms"))
        context = _make_context("key-1")
        captured = {}

        with patch(
            "gateway.session_context.set_session_vars",
            side_effect=lambda **kw: captured.update(kw) or [],
        ), patch(
            "tools.terminal_tool.record_session_cwd"
        ) as mock_record:
            runner._set_session_env(context)

        assert captured.get("cwd") == "/proj/botsms"
        assert captured.get("session_key") == "key-1"
        mock_record.assert_called_once_with("key-1", "/proj/botsms")

    def test_no_resolver_passes_empty_cwd_and_records_nothing(self):
        runner = _make_runner(None)
        context = _make_context("key-1")
        captured = {}

        with patch(
            "gateway.session_context.set_session_vars",
            side_effect=lambda **kw: captured.update(kw) or None,
        ), patch(
            "tools.terminal_tool.record_session_cwd"
        ) as mock_record:
            runner._set_session_env(context)

            assert captured.get("cwd") == ""
            mock_record.assert_not_called()

    def test_resolver_returning_none_passes_empty_cwd(self, monkeypatch):
        runner = _make_runner(_fake_resolver(None))
        context = _make_context("key-1")
        captured = {}

        with patch(
            "gateway.session_context.set_session_vars",
            side_effect=lambda **kw: captured.update(kw) or None,
        ), patch(
            "tools.terminal_tool.record_session_cwd"
        ) as mock_record:
            runner._set_session_env(context)

            assert captured.get("cwd") == ""
            mock_record.assert_not_called()

    def test_resolver_raising_falls_back_to_empty_cwd(self):
        def boom(session_key, source):
            raise RuntimeError("boom")

        runner = _make_runner(boom)
        context = _make_context("key-1")
        captured = {}

        with patch(
            "gateway.session_context.set_session_vars",
            side_effect=lambda **kw: captured.update(kw) or None,
        ), patch(
            "tools.terminal_tool.record_session_cwd"
        ) as mock_record:
            runner._set_session_env(context)

            assert captured.get("cwd") == ""
            mock_record.assert_not_called()
