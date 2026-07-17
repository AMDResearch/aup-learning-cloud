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
Auto Login Authenticator

For single-node deployments that require no authentication.
"""

from __future__ import annotations

from jupyterhub.auth import Authenticator
from jupyterhub.handlers import BaseHandler
from jupyterhub.utils import url_path_join


class AutoLoginAuthenticator(Authenticator):
    """
    Authenticator for single-node deployments.

    Automatically logs in users without requiring any credentials.
    WARNING: Only use in single-node, personal learning environments!
    """

    auto_login = True
    login_service = "Auto Login"

    def get_handlers(self, app):
        """Override to bypass login page and auto-authenticate."""

        class AutoLoginHandler(BaseHandler):
            """Handler that automatically authenticates and redirects to home."""

            async def get(self):
                """Auto-authenticate user on GET request."""
                username = "student"

                user = self.find_user(username)
                if user is None:
                    user = self.user_from_username(username)

                self.set_login_cookie(user)

                # Resolve the post-login destination via BaseHandler.get_next_url
                # so the value goes through JupyterHub's _validate_next_url,
                # which rejects cross-origin targets and normalises path-
                # confusion payloads (CVE-2026-33709 class). Reading
                # ``?next=`` directly and calling ``self.redirect`` would be
                # an open redirect — see the JupyterHub upstream LoginHandler
                # for the reference flow.
                next_url = self.get_next_url(user, default=url_path_join(self.hub.base_url, "home"))

                self.log.info(f"Auto-login: user '{username}' authenticated, redirecting to {next_url}")
                self.redirect(next_url)

            async def post(self):
                """Handle POST requests."""
                await self.get()

        return [
            (r"/login", AutoLoginHandler),
        ]
