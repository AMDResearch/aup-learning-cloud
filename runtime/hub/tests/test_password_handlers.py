import asyncio
import json
from types import SimpleNamespace

import pytest
from onboarding_handlers_support import DummyUser, FakeDb, load_handlers


@pytest.fixture
def loaded_handlers(monkeypatch: pytest.MonkeyPatch):
    with load_handlers(monkeypatch) as state:
        yield state


class PasswordAuthenticator:
    def __init__(self) -> None:
        self.changes: list[tuple[object, ...]] = []

    async def authenticate(self, _handler, data):
        return data["username"]

    def set_password(self, username, password, force_change=True):
        self.changes.append((username, password, force_change))
        return f"Password set for {username}"

    def mark_force_password_change(self, username, force):
        self.changes.append(("mark", username, force))

    def clear_force_password_change(self, username):
        self.changes.append(("clear", username))

    def batch_set_passwords(self, users, force_change=True):
        self.changes.extend((entry["username"], entry["password"], force_change) for entry in users)
        return {"success": len(users), "failed": 0, "results": []}


def configure_local_bootstrap(monkeypatch, handlers) -> None:
    monkeypatch.setitem(handlers._handler_config, "auth_mode", "local")
    monkeypatch.setenv("JUPYTERHUB_ADMIN_USERNAME", "operator")


def test_bootstrap_admin_can_change_own_password(loaded_handlers, monkeypatch) -> None:
    authenticator = PasswordAuthenticator()
    configure_local_bootstrap(monkeypatch, loaded_handlers.handlers)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: authenticator)
    handler = object.__new__(loaded_handlers.handlers.ChangePasswordHandler)
    handler.current_user = DummyUser("operator")
    handler.authenticator = object()
    handler.hub = SimpleNamespace(base_url="/hub/")
    handler.get_body_argument = lambda name, default=None: {
        "current_password": "OldPassword1!",
        "new_password": "NewPassword1!",
        "confirm_password": "NewPassword1!",
    }.get(name, default)
    handler.set_status = lambda status: setattr(handler, "status", status)
    handler.finish = lambda payload: setattr(handler, "body", payload)
    handler.redirect = lambda url: setattr(handler, "redirect_url", url)
    handler.render_template = lambda _name, **kwargs: kwargs["error_message"]

    asyncio.run(handler.post())

    assert handler.redirect_url == "/hub/auth/change-password?password_changed=1"
    assert authenticator.changes == [("operator", "NewPassword1!", False)]


def test_admin_can_reset_bootstrap_administrator(loaded_handlers, monkeypatch) -> None:
    authenticator = PasswordAuthenticator()
    configure_local_bootstrap(monkeypatch, loaded_handlers.handlers)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: authenticator)
    handler = object.__new__(loaded_handlers.handlers.AdminResetPasswordHandler)
    handler.current_user = DummyUser("manager", admin=True)
    handler.authenticator = object()
    handler.hub = SimpleNamespace(base_url="/hub/")
    handler.get_body_argument = lambda name, default=None: {
        "target_user": "operator",
        "new_password": "NewPassword1!",
        "confirm_password": "NewPassword1!",
        "force_change": "off",
    }.get(name, default)
    handler.redirect = lambda url: setattr(handler, "redirect_url", url)

    asyncio.run(handler.post())

    assert handler.redirect_url == "/hub/admin/reset-password?success=1&user=operator"
    assert authenticator.changes == [("operator", "NewPassword1!", False), ("clear", "operator")]


def test_admin_reset_listing_excludes_administrators_and_github_users(loaded_handlers) -> None:
    handler = object.__new__(loaded_handlers.handlers.AdminResetPasswordHandler)
    handler.current_user = DummyUser("operator", admin=True)
    handler.db = FakeDb(
        [
            DummyUser("operator", admin=True),
            DummyUser("admin", admin=True),
            DummyUser("learner"),
            DummyUser("github:octo"),
        ]
    )
    handler.get_argument = lambda _name, default="": default
    rendered = {}

    async def render_template(_name, **kwargs):
        rendered.update(kwargs)
        return "html"

    handler.render_template = render_template
    handler.finish = lambda _html: None

    asyncio.run(handler.get())

    assert rendered["native_users"] == ["learner"]


def test_admin_api_can_set_bootstrap_administrator_password(loaded_handlers, monkeypatch) -> None:
    authenticator = PasswordAuthenticator()
    configure_local_bootstrap(monkeypatch, loaded_handlers.handlers)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: authenticator)
    handler = object.__new__(loaded_handlers.handlers.AdminAPISetPasswordHandler)
    handler.current_user = DummyUser("manager", admin=True)
    handler.authenticator = object()
    handler.request = SimpleNamespace(body=b'{"username":"operator","password":"NewPassword1!"}')
    handler.set_header = lambda *_args: None
    handler.set_status = lambda status: setattr(handler, "status", status)
    handler.finish = lambda payload: setattr(handler, "body", payload)
    handler.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)

    asyncio.run(handler.post())

    assert json.loads(handler.body) == {"message": "Password set for operator"}
    assert authenticator.changes == [("operator", "NewPassword1!", True)]


def test_admin_api_keeps_other_local_users_changeable(loaded_handlers, monkeypatch) -> None:
    authenticator = PasswordAuthenticator()
    configure_local_bootstrap(monkeypatch, loaded_handlers.handlers)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: authenticator)
    handler = object.__new__(loaded_handlers.handlers.AdminAPISetPasswordHandler)
    handler.current_user = DummyUser("manager", admin=True)
    handler.authenticator = object()
    handler.request = SimpleNamespace(body=b'{"username":"learner","password":"NewPassword1!"}')
    handler.set_header = lambda *_args: None
    handler.finish = lambda payload: setattr(handler, "body", payload)
    handler.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)

    asyncio.run(handler.post())

    assert json.loads(handler.body) == {"message": "Password set for learner"}
    assert authenticator.changes == [("learner", "NewPassword1!", True)]


def test_admin_api_batch_can_set_bootstrap_administrator_password(loaded_handlers, monkeypatch) -> None:
    authenticator = PasswordAuthenticator()
    configure_local_bootstrap(monkeypatch, loaded_handlers.handlers)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: authenticator)
    handler = object.__new__(loaded_handlers.handlers.AdminAPIBatchSetPasswordHandler)
    handler.current_user = DummyUser("manager", admin=True)
    handler.authenticator = object()
    handler.request = SimpleNamespace(body=b'{"users":[{"username":"operator","password":"NewPassword1!"}]}')
    handler.set_header = lambda *_args: None
    handler.set_status = lambda status: setattr(handler, "status", status)
    handler.finish = lambda payload: setattr(handler, "body", payload)
    handler.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)

    asyncio.run(handler.post())

    assert json.loads(handler.body)["success"] == 1
    assert authenticator.changes == [("operator", "NewPassword1!", True)]


def test_github_users_remain_blocked_from_native_password_changes(loaded_handlers, monkeypatch) -> None:
    authenticator = PasswordAuthenticator()
    configure_local_bootstrap(monkeypatch, loaded_handlers.handlers)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: authenticator)
    handler = object.__new__(loaded_handlers.handlers.AdminAPISetPasswordHandler)
    handler.current_user = DummyUser("manager", admin=True)
    handler.authenticator = object()
    handler.request = SimpleNamespace(body=b'{"username":"github:octo","password":"NewPassword1!"}')
    handler.set_header = lambda *_args: None
    handler.set_status = lambda status: setattr(handler, "status", status)
    handler.finish = lambda payload: setattr(handler, "body", payload)
    handler.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)

    asyncio.run(handler.post())

    assert handler.status == 400
    assert json.loads(handler.body) == {"error": "Cannot set password for GitHub users"}
    assert authenticator.changes == []


def test_admin_provisioning_rejects_username_that_local_login_would_reject(loaded_handlers, monkeypatch) -> None:
    class LoginAuthenticator:
        def validate_username(self, username):
            return username == username.lower() and ":" not in username

    class NativeAuthenticator:
        def normalize_username(self, username):
            return username.lower()

        def _check_password_strength(self, _password):
            return None

        def set_password(self, *_args, **_kwargs):
            raise AssertionError("invalid username must not set a password")

    handler = object.__new__(loaded_handlers.handlers.AdminAPIProvisionUsersHandler)
    handler.current_user = DummyUser("operator", admin=True)
    handler.authenticator = LoginAuthenticator()
    handler.request = SimpleNamespace(body=b'{"users":[{"username":"Admin","password":"Password1!"}]}')
    handler.find_user = lambda _username: None
    handler.set_header = lambda *_args: None
    handler.finish = lambda payload: setattr(handler, "body", payload)
    handler.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)
    monkeypatch.setattr(loaded_handlers.handlers, "_find_firstuse_authenticator", lambda _auth: NativeAuthenticator())

    asyncio.run(handler.post())

    payload = json.loads(handler.body)
    assert payload["failed"] == 1
    assert payload["results"][0]["error"] == "Invalid username: Admin"


def test_password_handlers_find_native_authenticator_directly_and_in_composition(loaded_handlers) -> None:
    native = loaded_handlers.native_authenticator()
    composed = loaded_handlers.multi_authenticator()
    composed._authenticators = [native]

    assert loaded_handlers.handlers._find_firstuse_authenticator(native) is native
    assert loaded_handlers.handlers._find_firstuse_authenticator(composed) is native
