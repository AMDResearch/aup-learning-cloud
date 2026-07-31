import re

from core.authenticators.firstuse import CustomFirstUseAuthenticator

LOCAL_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class CustomLocalAuthenticator(CustomFirstUseAuthenticator):
    async def authenticate(self, _handler, data):
        username = data.get("username", "")
        password = data.get("password", "")
        if not LOCAL_USERNAME_PATTERN.fullmatch(username) or not password:
            return None
        if not self._user_exists(username):
            return None
        if not self.check_password(username, password):
            return None
        return username
