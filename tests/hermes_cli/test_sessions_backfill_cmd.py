"""CLI `hermes sessions backfill` — flag resolution and safety.

The backfill command stamps a cwd onto workspace-less rows (Home bucket).
These tests pin the target resolution (default active project, --cwd,
--project by id or slug), the --dry-run no-write guarantee, and the
both-flags conflict error.

The hermetic conftest already redirects ``HERMES_HOME`` per test, so
``get_hermes_home()`` resolves to a tempdir here; both the seeded rows and
the handler's argless ``SessionDB()`` must land on that same home.
"""

from argparse import Namespace

import hermes_cli.sessions_cmd as sc


def _args(action, **kw):
    base = dict(
        sessions_action=action,
        session_id=None, title=None, yes=True, source=None, path=None,
        from_source=None, dry_run=False, older_than=None, newer_than=None,
        before=None, after=None, limit=50,
        cwd=None, project=None, no_backup=False,
    )
    base.update(kw)
    return Namespace(**base)


def _home(tmp_path):
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    # get_hermes_home() must be inside this test's tmp_path — the hermetic
    # fixture guarantees it; assert so a stray env leak is loud, not silent.
    assert str(home.resolve()).startswith(str(tmp_path.resolve()))
    return home


def _seed(tmp_path):
    """state.db with one unbound row; projects.db with one project."""
    home = _home(tmp_path)
    from hermes_state import SessionDB
    db = SessionDB(home / "state.db")
    db.create_session(session_id="s_unbound", source="telegram")
    db.close()
    from hermes_cli import projects_db
    with projects_db.connect(home / "projects.db") as conn:
        pid = projects_db.create_project(
            conn,
            name="mesax",
            slug="mesax",
            primary_path=str(home / "mesax"),
        )
        projects_db.set_active(conn, pid)
    (home / "mesax").mkdir()
    return pid


def test_dry_run_active_project_lists_and_does_not_write(tmp_path, capsys):
    _seed(tmp_path)
    rc = sc.cmd_sessions(_args("backfill", dry_run=True))
    out = capsys.readouterr().out
    assert rc in (None, 0)
    assert "s_unbound" in out
    assert "--dry-run" in out

    from hermes_state import SessionDB
    db = SessionDB(_home(tmp_path) / "state.db")
    row = db._conn.execute(
        "SELECT cwd FROM sessions WHERE id = 's_unbound'"
    ).fetchone()
    db.close()
    assert row["cwd"] is None  # dry-run never writes


def test_project_flag_targets_specific_project(tmp_path, capsys):
    _seed(tmp_path)
    rc = sc.cmd_sessions(_args("backfill", dry_run=True, project="mesax"))
    out = capsys.readouterr().out
    assert rc in (None, 0)
    assert f"Target workspace: {_home(tmp_path) / 'mesax'}" in out


def test_project_flag_unknown_project_errors(tmp_path, capsys):
    _seed(tmp_path)
    rc = sc.cmd_sessions(_args("backfill", project="nope"))
    out = capsys.readouterr().out
    assert rc == 2
    assert "no project matches" in out.lower()


def test_cwd_and_project_conflict_errors(tmp_path, capsys):
    _seed(tmp_path)
    rc = sc.cmd_sessions(
        _args("backfill", cwd=str(_home(tmp_path)), project="mesax")
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert "not both" in out.lower()


def test_no_active_project_no_cwd_errors(tmp_path, capsys):
    home = _home(tmp_path)
    from hermes_state import SessionDB
    db = SessionDB(home / "state.db")
    db.create_session(session_id="s_unbound", source="telegram")
    db.close()
    # no projects.db at all → no active project
    rc = sc.cmd_sessions(_args("backfill"))
    out = capsys.readouterr().out
    assert rc == 2
    assert "no active project" in out.lower()


def test_cwd_flag_stamps_all_unbound(tmp_path, capsys, monkeypatch):
    home = _home(tmp_path)
    _seed(tmp_path)
    monkeypatch.setattr(sc, "_confirm_prompt", lambda prompt: True)
    rc = sc.cmd_sessions(_args("backfill", cwd=str(home / "mesax")))
    out = capsys.readouterr().out
    assert rc in (None, 0)
    assert "Stamped" in out

    from hermes_state import SessionDB
    db = SessionDB(home / "state.db")
    row = db._conn.execute(
        "SELECT cwd FROM sessions WHERE id = 's_unbound'"
    ).fetchone()
    db.close()
    assert row["cwd"] == str(home / "mesax")
