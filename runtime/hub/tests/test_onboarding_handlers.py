import asyncio
import json
from datetime import datetime, timezone

import pytest
from onboarding_handlers_support import FakeDb, fake_session_scope, load_handlers, make_handler


@pytest.fixture
def loaded_handlers(monkeypatch: pytest.MonkeyPatch):
    with load_handlers(monkeypatch) as state:
        yield state


def test_get_my_onboarding_returns_visible_when_no_state_exists(loaded_handlers, monkeypatch) -> None:
    monkeypatch.setattr(loaded_handlers.database, "session_scope", lambda: fake_session_scope(FakeDb()))
    handler, captured = make_handler(loaded_handlers.handlers.GetMyOnboardingHandler, "alice")

    asyncio.run(handler.get())

    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["body"]) == {"should_show": True, "dismissed_at": None}


def test_get_my_onboarding_returns_hidden_when_current_user_already_dismissed(loaded_handlers, monkeypatch) -> None:
    class DetachedAwareState:
        def __init__(self, username: str, dismissed_at: datetime) -> None:
            self.username = username
            self._dismissed_at = dismissed_at
            self.detached = False

        @property
        def dismissed_at(self) -> datetime:
            if self.detached:
                raise RuntimeError("detached instance access")
            return self._dismissed_at

    dismissed_at = datetime(2026, 4, 22, 12, 30, tzinfo=timezone.utc)
    state = DetachedAwareState(username="alice", dismissed_at=dismissed_at)
    monkeypatch.setattr(loaded_handlers.database, "session_scope", lambda: fake_session_scope(FakeDb([state])))
    handler, captured = make_handler(loaded_handlers.handlers.GetMyOnboardingHandler, "alice")

    asyncio.run(handler.get())

    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["body"]) == {"should_show": False, "dismissed_at": dismissed_at.isoformat()}


def test_dismiss_my_onboarding_persists_dismissal_for_current_user(loaded_handlers, monkeypatch) -> None:
    existing_state = loaded_handlers.models.UserOnboardingState(
        username="bob",
        dismissed_at=datetime(2026, 4, 21, 8, tzinfo=timezone.utc),
    )
    db = FakeDb([existing_state])
    monkeypatch.setattr(loaded_handlers.database, "session_scope", lambda: fake_session_scope(db))
    handler, captured = make_handler(loaded_handlers.handlers.DismissMyOnboardingHandler, "alice")

    asyncio.run(handler.post())

    payload = json.loads(captured["body"])
    dismissed_at = datetime.fromisoformat(payload["dismissed_at"])
    assert captured["headers"]["Content-Type"] == "application/json"
    assert payload["should_show"] is False
    assert payload["dismissed_at"] is not None
    assert dismissed_at.tzinfo == timezone.utc
    assert db.commits == 1
    assert len(db.rows) == 2
    assert db.rows[0].username == "bob"
    assert db.rows[1].username == "alice"
    assert db.rows[1].dismissed_at == dismissed_at
