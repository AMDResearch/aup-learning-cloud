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

from core.authenticators.firstuse import CustomFirstUseAuthenticator


class CustomMultiAuthenticator(MultiAuthenticator):
    """
    MultiAuthenticator with custom login page HTML and refresh_user support.

    Provides a unified login page supporting multiple authentication methods.
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

    def add_user(self, user):
        from core.authenticators.github_app import GITHUB_USERNAME_PREFIX

        authenticator = self._find_authenticator_for_user(user)
        if user.name.startswith(GITHUB_USERNAME_PREFIX) and authenticator is not None:
            authenticator.add_user(user)
        return super().add_user(user)

    def delete_user(self, user):
        from core.authenticators.github_app import GITHUB_USERNAME_PREFIX

        authenticator = self._find_authenticator_for_user(user)
        if user.name.startswith(GITHUB_USERNAME_PREFIX) and authenticator is not None:
            authenticator.delete_user(user)
        return super().delete_user(user)

    def get_custom_html(self, base_url):
        html = []

        for authenticator in self._authenticators:
            name = getattr(authenticator, "service_name", "authenticator")
            login_service = getattr(authenticator, "login_service", name)
            url = authenticator.login_url(base_url)

            match authenticator:
                case CustomFirstUseAuthenticator():
                    html.append(f"""
                <div class="login-option mb-6 bg-white rounded-xl shadow-lg p-6">
                <form action="{url}{{% if next is defined and next|length %}}?next={{{{ next | urlencode }}}}{{% endif %}}" method="post">
                    <input type="hidden" name="_xsrf" value="{{{{ xsrf }}}}" />
                    <div class="mb-4">
                    <input type="text" name="username" placeholder="Username"
                            aria-label="Username"
                            class="block w-full px-4 py-2 border rounded-md shadow-sm focus:ring-2 focus:ring-blue-500"
                            required />
                    </div>
                    <div class="mb-4 relative">
                    <input type="password" name="password" placeholder="Password"
                            aria-label="Password" autocomplete="current-password"
                            class="login-input block w-full pl-4 pr-10 py-2 rounded-md shadow-sm focus:ring-2 focus:ring-blue-500"
                            required />
                    <button type="button" class="password-toggle absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600" aria-label="Show password">
                        <svg class="eye-open w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                        <svg class="eye-closed w-5 h-5 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
                    </button>
                    </div>
                    <button type="submit"
                            class="login-submit w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md">
                    Use LocalAccount Login
                    </button>
                </form>
                </div>
                """)
                case _:
                    html.append(f"""
                <div class="login-option mb-4">
                <a role="button" class="login-github-button w-full inline-block text-center py-3 px-4 bg-gray-800
                                    rounded-md hover:bg-gray-900 font-medium"
                    href="{url}{{% if next is defined and next|length %}}?next={{{{ next }}}}{{% endif %}}">
                    Use {login_service} Login
                </a>
                </div>
                """)

        return "\n".join(html)
