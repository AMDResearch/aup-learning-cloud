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
GitHub App Authenticator

Custom GitHub App authenticator with team integration support.
Supports automatic token refresh for GitHub App user-to-server tokens.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

from oauthenticator.github import GitHubOAuthenticator
from oauthenticator.oauth2 import OAuthCallbackHandler
from traitlets import Int, Unicode

log = logging.getLogger("jupyterhub.auth.github")

GITHUB_USERNAME_PREFIX = "github:"


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
    """GitHub App authenticator with access token preservation and refresh."""

    name = "github"
    prefix = GITHUB_USERNAME_PREFIX
    url_scope = "/github"
    callback_handler = _GitHubAppInstallCallbackHandler

    app_id = Unicode(
        "",
        config=True,
        help="GitHub App ID used to create installation access tokens for platform-owned API calls.",
    )

    installation_id = Unicode(
        "",
        config=True,
        help="GitHub App installation ID used for platform-owned team synchronization.",
    )

    private_key_file = Unicode(
        "",
        config=True,
        help="Path to the mounted GitHub App private key PEM file used for installation token creation.",
    )

    private_key = Unicode(
        "",
        config=True,
        help="GitHub App private key PEM content used for installation token creation when no file path is set.",
    )

    team_sync_ttl_seconds = Int(
        3600,
        config=True,
        help="TTL in seconds for GitHub team membership sync caches.",
    )

    def _with_github_username_prefix(self, auth_model):
        auth_model = auth_model.copy()
        if not auth_model["name"].startswith(self.prefix):
            auth_model["name"] = f"{self.prefix}{auth_model['name']}"
        return auth_model

    async def run_post_auth_hook(self, handler, auth_model):
        auth_model = await super().run_post_auth_hook(handler, auth_model)
        return self._with_github_username_prefix(auth_model)

    def add_user(self, user):
        return super().add_user(SimpleNamespace(name=user.name.removeprefix(self.prefix)))

    def delete_user(self, user):
        return super().delete_user(SimpleNamespace(name=user.name.removeprefix(self.prefix)))

    def login_url(self, base_url):
        if type(self) is CustomGitHubOAuthenticator:
            base_url = f"{base_url.rstrip('/')}{self.url_scope}"
        return super().login_url(base_url)

    def get_handlers(self, app):
        handlers = super().get_handlers(app)
        if type(self) is CustomGitHubOAuthenticator:
            return [(f"{self.url_scope}{path}", handler) for path, handler in handlers]
        return handlers

    def get_callback_url(self, handler=None):
        if self.oauth_callback_url:
            if not self.oauth_callback_url.endswith(f"{self.url_scope}/oauth_callback"):
                raise ValueError("GitHub oauth_callback_url must end in /hub/github/oauth_callback")
            return self.oauth_callback_url
        callback_url = super().get_callback_url(handler)
        if callback_url.endswith(f"{self.url_scope}/oauth_callback"):
            return callback_url
        return f"{callback_url.removesuffix('/oauth_callback')}{self.url_scope}/oauth_callback"

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

        try:
            auth_state = await user.get_auth_state()
        except Exception:
            log.warning(
                "Failed to read auth_state for %s; keeping current session without forcing OAuth",
                user.name,
                exc_info=True,
            )
            return True

        if not auth_state:
            log.warning("No readable auth_state for %s; keeping current session without forcing OAuth", user.name)
            return True

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
                    "Proactive token refresh failed for %s; keeping current session without retrying OAuth",
                    user.name,
                    exc_info=True,
                )
                return True

            # Keep old refresh_token if the response doesn't include a new one
            if not token_info.get("refresh_token"):
                token_info["refresh_token"] = refresh_token

            expires_in = token_info.get("expires_in")
            try:
                auth_model = await self._token_to_auth_model(token_info)
            except Exception:
                log.error(
                    "Fresh token from proactive refresh failed for %s; keeping current session",
                    user.name,
                    exc_info=True,
                )
                return True

            if expires_in is not None:
                auth_model["auth_state"]["expires_at"] = time.time() + int(expires_in)

            return self._with_github_username_prefix(auth_model)

        # Not close to expiry. Avoid the parent refresh path here because it
        # may make external GitHub validation calls for every auth_refresh_age
        # interval even though our cached auth_state is still usable.
        return True
