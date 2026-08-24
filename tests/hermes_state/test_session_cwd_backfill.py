"""SessionDB backfill helpers for workspace-less (Home-bucket) rows."""

from hermes_state import SessionDB


def _mkdb(tmp_path):
    return SessionDB(db_path=tmp_path / "state.db")


def _insert(db, session_id, source="telegram", cwd=None, git_repo_root=None):
    db.create_session(
        session_id=session_id,
        source=source,
        cwd=cwd,
        git_repo_root=git_repo_root,
    )


class TestListUnboundSessions:
    def test_only_rows_without_cwd_and_git_root_are_listed(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd=None)
        _insert(db, "s2", cwd="/x")          # has cwd → not unbound
        _insert(db, "s3", git_repo_root="/g")  # has git root → not unbound
        _insert(db, "s4", source="tool")     # tool rows are excluded
        unbound = db.list_unbound_sessions()
        ids = {r["id"] for r in unbound}
        assert ids == {"s1"}

    def test_empty_when_all_bound(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd="/x")
        assert db.list_unbound_sessions() == []


class TestBackfillSessionCwd:
    def test_stamps_only_null_cwd_rows(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd=None)
        _insert(db, "s2", cwd=None)
        _insert(db, "s3", cwd="/keep")
        updated = db.backfill_session_cwd("/new", ["s1", "s2", "s3"])
        assert updated == 2
        for sid, expected in (("s1", "/new"), ("s2", "/new"), ("s3", "/keep")):
            row = db._conn.execute(
                "SELECT cwd FROM sessions WHERE id = ?", (sid,)
            ).fetchone()
            assert row["cwd"] == expected

    def test_idempotent(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd=None)
        assert db.backfill_session_cwd("/x", ["s1"]) == 1
        assert db.backfill_session_cwd("/x", ["s1"]) == 0

    def test_noop_without_ids_or_cwd(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd=None)
        assert db.backfill_session_cwd("", ["s1"]) == 0
        assert db.backfill_session_cwd("/x", []) == 0


class TestClearSessionCwd:
    def test_detaches_row_to_home(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd="/project/a", git_repo_root="/project")
        db.update_session_cwd(
            "s1", "/project/a", "main", "/project", replace_git_meta=True
        )
        generation = db.clear_session_cwd("s1")
        row = db._conn.execute(
            "SELECT cwd, git_branch, git_repo_root, git_metadata_generation "
            "FROM sessions WHERE id = ?",
            ("s1",),
        ).fetchone()
        assert row["cwd"] is None
        assert row["git_branch"] is None
        assert row["git_repo_root"] is None
        assert row["git_metadata_generation"] == generation
        assert generation is not None and generation >= 1

    def test_unknown_session_returns_none(self, tmp_path):
        db = _mkdb(tmp_path)
        assert db.clear_session_cwd("missing") is None

    def test_noop_without_id(self, tmp_path):
        db = _mkdb(tmp_path)
        assert db.clear_session_cwd("") is None

    def test_idempotent(self, tmp_path):
        db = _mkdb(tmp_path)
        _insert(db, "s1", cwd="/project")
        first = db.clear_session_cwd("s1")
        second = db.clear_session_cwd("s1")
        row = db._conn.execute(
            "SELECT cwd FROM sessions WHERE id = ?", ("s1",)
        ).fetchone()
        assert row["cwd"] is None
        # Second clear still bumps the generation (a move claim that must win).
        assert first is not None and second is not None
        assert second > first
