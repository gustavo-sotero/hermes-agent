"""Gateway cwd-resolver precedence and junk filtering."""

import os

from gateway.cwd_resolver import _is_junk_root, _valid_cwd, build_gateway_cwd_resolver


class TestJunkFilter:
    def test_home_dir_is_junk(self, tmp_path):
        assert _is_junk_root(str(tmp_path), str(tmp_path)) is True

    def test_hermes_home_subtree_is_junk(self, tmp_path):
        hermes_home = tmp_path / "hermes"
        child = hermes_home / "sessions"
        assert _is_junk_root(str(child), str(hermes_home)) is True

    def test_sibling_dir_is_not_junk(self, tmp_path):
        hermes_home = tmp_path / "hermes"
        project = tmp_path / "portfolio" / "mesax"
        assert _is_junk_root(str(project), str(hermes_home)) is False


class TestValidCwd:
    def test_returns_existing_non_junk_dir(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        hermes_home = tmp_path / "hermes"
        assert _valid_cwd(str(project), str(hermes_home)) == str(project)

    def test_rejects_missing_dir(self, tmp_path):
        hermes_home = tmp_path / "hermes"
        assert _valid_cwd(str(tmp_path / "nope"), str(hermes_home)) is None

    def test_rejects_junk_root(self, tmp_path):
        hermes_home = tmp_path / "hermes"
        assert _valid_cwd(str(tmp_path), str(hermes_home)) is None

    def test_rejects_empty_and_non_string(self, tmp_path):
        hermes_home = tmp_path / "hermes"
        assert _valid_cwd("", str(hermes_home)) is None
        assert _valid_cwd(None, str(hermes_home)) is None


class TestResolverPrecedence:
    def test_session_record_wins_over_active_project(self, tmp_path):
        recorded = tmp_path / "recorded"
        recorded.mkdir()
        active = tmp_path / "active"
        active.mkdir()
        resolver = build_gateway_cwd_resolver(
            terminal_cwd="",
            hermes_home=str(tmp_path / "hermes"),
            projects_db_path=str(tmp_path / "projects.db"),
            get_session_cwd=lambda key: str(recorded),
            get_active_project_path=lambda: str(active),
        )
        assert resolver("key1", None) == str(recorded)

    def test_active_project_fallback(self, tmp_path):
        active = tmp_path / "active"
        active.mkdir()
        resolver = build_gateway_cwd_resolver(
            terminal_cwd="",
            hermes_home=str(tmp_path / "hermes"),
            projects_db_path=str(tmp_path / "projects.db"),
            get_session_cwd=lambda key: None,
            get_active_project_path=lambda: str(active),
        )
        assert resolver("key1", None) == str(active)

    def test_terminal_cwd_last_resort(self, tmp_path):
        term = tmp_path / "term"
        term.mkdir()
        resolver = build_gateway_cwd_resolver(
            terminal_cwd=str(term),
            hermes_home=str(tmp_path / "hermes"),
            projects_db_path=str(tmp_path / "projects.db"),
            get_session_cwd=lambda key: None,
            get_active_project_path=lambda: None,
        )
        assert resolver("key1", None) == str(term)

    def test_nothing_resolves_returns_none(self, tmp_path):
        resolver = build_gateway_cwd_resolver(
            terminal_cwd="",
            hermes_home=str(tmp_path / "hermes"),
            projects_db_path=str(tmp_path / "projects.db"),
            get_session_cwd=lambda key: None,
            get_active_project_path=lambda: None,
        )
        assert resolver("key1", None) is None

    def test_junk_terminal_cwd_ignored(self, tmp_path):
        # terminal.cwd resolving to the bare home dir must NOT be stamped
        hermes_home = tmp_path / "hermes"
        resolver = build_gateway_cwd_resolver(
            terminal_cwd=str(tmp_path),
            hermes_home=str(hermes_home),
            projects_db_path=str(tmp_path / "projects.db"),
            get_session_cwd=lambda key: None,
            get_active_project_path=lambda: None,
        )
        assert resolver("key1", None) is None
