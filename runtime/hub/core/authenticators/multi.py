# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Multi Authenticator

Provides support for multiple authentication methods on a single login page.
"""

from __future__ import annotations

from multiauthenticator import MultiAuthenticator
from multiauthenticator.multiauthenticator import PREFIX_SEPARATOR


class CustomMultiAuthenticator(MultiAuthenticator):
    """
    MultiAuthenticator with refresh_user support.

    Delegates ``refresh_user`` to the sub-authenticator that owns the user.
    """

    def validate_username(self, username):
        """Reject usernames that could spoof a prefixed authenticator."""
        if not super().validate_username(username):
            return False
        # Only local (unprefixed) accounts need checking.
        # Prefixed names like "github:user" are created by the OAuth flow
        # itself and are legitimate; block them only when they don't come
        # from a registered prefix.
        if PREFIX_SEPARATOR in username:
            known_prefixes = [a.username_prefix for a in self._authenticators if a.username_prefix]
            if not any(username.startswith(p) for p in known_prefixes):
                return False
        return True

    def _find_authenticator_for_user(self, user):
        """Return the sub-authenticator whose prefix matches *user.name*.

        Authenticators with a non-empty prefix are checked first so that
        a catch-all empty prefix (local accounts) never shadows others.
        """
        fallback = None
        for authenticator in self._authenticators:
            prefix = authenticator.username_prefix
            if not prefix:
                fallback = authenticator
                continue
            if user.name.startswith(prefix):
                return authenticator
        return fallback

    async def refresh_user(self, user, handler=None):
        authenticator = self._find_authenticator_for_user(user)
        if authenticator is None:
            return True
        return await authenticator.refresh_user(user, handler)

    async def add_user(self, user):
        """Delegate to the sub-authenticator that owns the user.

        Children may be coroutines (they sync groups at login), so route the
        call through maybe_future.
        """
        authenticator = self._find_authenticator_for_user(user)
        if authenticator is not None:
            from jupyterhub.utils import maybe_future

            await maybe_future(authenticator.add_user(user))
        return super().add_user(user)

    def delete_user(self, user):
        from core.authenticators.github_app import GITHUB_USERNAME_PREFIX

        authenticator = self._find_authenticator_for_user(user)
        if user.name.startswith(GITHUB_USERNAME_PREFIX) and authenticator is not None:
            authenticator.delete_user(user)
        return super().delete_user(user)

    def get_custom_html(self, base_url: str) -> str:
        return ""
