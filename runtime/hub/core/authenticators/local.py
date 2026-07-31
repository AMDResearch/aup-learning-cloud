from core.authenticators.firstuse import CustomFirstUseAuthenticator


class CustomLocalAuthenticator(CustomFirstUseAuthenticator):
    async def authenticate(self, _handler, data):
        username = self.normalize_username(data.get("username", ""))
        password = data.get("password", "")
        if not username or not password or ":" in username:
            return None
        if not self._user_exists(username):
            return None
        if not self.check_password(username, password):
            return None
        return username
