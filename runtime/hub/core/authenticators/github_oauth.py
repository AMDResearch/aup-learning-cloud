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
GitHub OAuth Authenticator

Custom GitHub OAuth authenticator with team integration support.
Supports automatic token refresh for GitHub App user-to-server tokens.
"""

from __future__ import annotations

import logging
import time

from oauthenticator.github import GitHubOAuthenticator
from oauthenticator.oauth2 import OAuthCallbackHandler

log = logging.getLogger("jupyterhub.auth.github")


class _GitHubAppInstallCallbackHandler(OAuthCallbackHandler):
    """Callback handler that gracefully handles GitHub App installation redirects.

    When a user installs/requests a GitHub App, GitHub redirects to the OAuth
    callback URL with ``setup_action`` (install, request, etc.) but without the
    ``state`` parameter that the standard OAuth flow requires.  Instead of
    returning a 400 error, detect this case and redirect the user back to the
    spawn page.
    """

    async def get(self):
        if self.get_argument("setup_action", "") and not self.get_argument("state", ""):
            self.redirect(self.hub.base_url + "spawn")
            return
        await super().get()


class CustomGitHubOAuthenticator(GitHubOAuthenticator):
    """GitHub OAuth authenticator with access token preservation and refresh."""

    name = "github"
    callback_handler = _GitHubAppInstallCallbackHandler

    async def authenticate(self, handler, data=None):
        result = await super().authenticate(handler, data)
        if not result:
            return None

        # Store expires_at timestamp for proactive refresh checks.
        # The parent class already stores refresh_token via build_auth_state_dict.
        token_response = result["auth_state"].get("token_response", {})
        expires_in = token_response.get("expires_in")
        if expires_in is not None:
            result["auth_state"]["expires_at"] = time.time() + int(expires_in)

        return result

    async def refresh_user(self, user, handler=None, **kwargs):
        """Refresh user token, with proactive refresh before expiry.

        If the token has an ``expires_at`` timestamp and is within 10 minutes
        of expiring, proactively refresh it instead of waiting for a 401.
        When no ``refresh_token`` is present (token expiration disabled on the
        GitHub App), skip refresh and return ``True``.
        """
        if not self.enable_auth_state:
            return True

        auth_state = await user.get_auth_state()
        if not auth_state:
            return False

        refresh_token = auth_state.get("refresh_token")

        # No refresh_token means token expiration is disabled — nothing to do
        if not refresh_token:
            return True

        # Proactively refresh if within 10 minutes of expiry
        expires_at = auth_state.get("expires_at")
        if expires_at and time.time() > expires_at - 600:
            log.info(
                "Token for %s expires soon (at %s), proactively refreshing",
                user.name,
                time.ctime(expires_at),
            )
            refresh_params = self.build_refresh_token_request_params(refresh_token)
            try:
                token_info = await self.get_token_info(handler, refresh_params)
            except Exception:
                log.warning(
                    "Proactive token refresh failed for %s, falling back to parent",
                    user.name,
                    exc_info=True,
                )
                return await super().refresh_user(user, handler, **kwargs)

            # Keep old refresh_token if the response doesn't include a new one
            if not token_info.get("refresh_token"):
                token_info["refresh_token"] = refresh_token

            expires_in = token_info.get("expires_in")
            try:
                auth_model = await self._token_to_auth_model(token_info)
            except Exception:
                log.error(
                    "Fresh token from proactive refresh failed for %s",
                    user.name,
                    exc_info=True,
                )
                return False

            if expires_in is not None:
                auth_model["auth_state"]["expires_at"] = time.time() + int(expires_in)

            return auth_model

        # Not close to expiry — let the parent handle the standard flow
        return await super().refresh_user(user, handler, **kwargs)
