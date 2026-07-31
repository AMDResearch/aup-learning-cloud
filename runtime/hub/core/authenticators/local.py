import re

from core.authenticators.firstuse import CustomFirstUseAuthenticator

LOCAL_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class CustomLocalAuthenticator(CustomFirstUseAuthenticator):
    def validate_username(self, username):
        return bool(LOCAL_USERNAME_PATTERN.fullmatch(username))

    def _user_exists(self, username):
        db = getattr(self, "db", None) or getattr(getattr(self, "parent", None), "db", None)
        if db is None:
            return False
        try:
            from jupyterhub.orm import User

            return db.query(User).filter_by(name=username).first() is not None
        except Exception:
            return False

    async def authenticate(self, _handler, data):
        username = data.get("username", "")
        password = data.get("password", "")
        if not self.validate_username(username) or not password:
            return None
        if not self._user_exists(username):
            return None
        if not self.check_password(username, password):
            return None
        return username
