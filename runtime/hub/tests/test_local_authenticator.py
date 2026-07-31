import asyncio
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_AUTHENTICATOR = ROOT / "core" / "authenticators" / "local.py"


class FakeFirstUseAuthenticator:
    def normalize_username(self, username):
        return username.lower()

    def _user_exists(self, username):
        return username == "existing"

    def check_password(self, username, password):
        return username == "existing" and password == "correct-password"


def test_local_authenticator_rejects_first_use_and_accepts_existing_password() -> None:
    core = types.ModuleType("core")
    authenticators = types.ModuleType("core.authenticators")
    firstuse = types.ModuleType("core.authenticators.firstuse")
    firstuse.CustomFirstUseAuthenticator = FakeFirstUseAuthenticator
    sys.modules.update(
        {
            "core": core,
            "core.authenticators": authenticators,
            "core.authenticators.firstuse": firstuse,
        }
    )
    spec = importlib.util.spec_from_file_location("core.authenticators.local", LOCAL_AUTHENTICATOR)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    authenticator = module.CustomLocalAuthenticator()

    assert asyncio.run(authenticator.authenticate(None, {"username": "EXISTING", "password": "correct-password"})) == "existing"
    assert asyncio.run(authenticator.authenticate(None, {"username": "existing", "password": "wrong-password"})) is None
    assert asyncio.run(authenticator.authenticate(None, {"username": "new", "password": "valid-password"})) is None
