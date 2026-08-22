"""Messaging sessions persist a cwd so they leave the sidebar "Home" bucket.

Regression tests for the gateway-side fix: a ``cwd_resolver`` injected on the
SessionStore populates ``sessions.cwd`` at row creation and peer refresh
(NULL-only), so ``project_tree`` can place the row under a project.
"""

from gateway.session import SessionStore, SessionSource
from gateway.config import GatewayConfig, Platform
from hermes_state import SessionDB


def _make_store(tmp_path, resolver=None):
    store = SessionStore(sessions_dir=tmp_path, config=GatewayConfig())
    store._db = SessionDB(db_path=tmp_path / "state.db")
    store.cwd_resolver = resolver
    return store


def _make_source():
    return SessionSource(platform=Platform.TELEGRAM, chat_id="123", user_id="u1")


def _row_cwd(db, session_id):
    row = db._conn.execute(
        "SELECT cwd FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    return row["cwd"] if row else None


class TestSessionCwdAtCreation:
    def test_resolver_result_persisted_on_row_creation(self, tmp_path):
        store = _make_store(tmp_path, resolver=lambda key, source: str(tmp_path))
        entry = store.get_or_create_session(_make_source())
        store._db.create_session(session_id=entry.session_id, source="telegram")
        assert _row_cwd(store._db, entry.session_id) == str(tmp_path)

    def test_no_resolver_leaves_row_without_cwd(self, tmp_path):
        store = _make_store(tmp_path, resolver=None)
        entry = store.get_or_create_session(_make_source())
        store._db.create_session(session_id=entry.session_id, source="telegram")
        assert _row_cwd(store._db, entry.session_id) is None

    def test_resolver_returning_missing_dir_yields_no_cwd(self, tmp_path):
        store = _make_store(
            tmp_path,
            resolver=lambda k, s: str(tmp_path / "does-not-exist"),
        )
        entry = store.get_or_create_session(_make_source())
        store._db.create_session(session_id=entry.session_id, source="telegram")
        assert _row_cwd(store._db, entry.session_id) is None


class TestPeerRefreshBackfill:
    def test_peer_refresh_stamps_cwd_on_null_row(self, tmp_path):
        store = _make_store(tmp_path, resolver=lambda k, s: "/tmp")
        entry = store.get_or_create_session(_make_source())
        store._db.create_session(session_id=entry.session_id, source="telegram")
        assert _row_cwd(store._db, entry.session_id) == "/tmp"

    def test_peer_refresh_never_overwrites_existing_cwd(self, tmp_path):
        cwd_a = tmp_path / "cwd-a"
        cwd_b = tmp_path / "cwd-b"
        cwd_a.mkdir()
        cwd_b.mkdir()
        store = _make_store(tmp_path, resolver=lambda k, s: str(cwd_a))
        entry = store.get_or_create_session(_make_source())
        store._db.create_session(session_id=entry.session_id, source="telegram")
        assert _row_cwd(store._db, entry.session_id) == str(cwd_a)

        # Resolver answer changes; a peer refresh must NOT clobber the cwd
        # already recorded on the row (COALESCE-only write).
        store.cwd_resolver = lambda k, s: str(cwd_b)
        store._record_gateway_session_peer(
            entry.session_id, entry.session_key, _make_source()
        )
        assert _row_cwd(store._db, entry.session_id) == str(cwd_a)
