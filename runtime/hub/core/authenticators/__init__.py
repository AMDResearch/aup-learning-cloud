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
Authenticator Package

Provides various authentication methods for JupyterHub.
"""

from core.authenticators.auto_login import AutoLoginAuthenticator
from core.authenticators.firstuse import CustomFirstUseAuthenticator
from core.authenticators.github_app import GITHUB_USERNAME_PREFIX, CustomGitHubOAuthenticator
from core.authenticators.jwt import RemoteLabAuthenticator
from core.authenticators.multi import CustomMultiAuthenticator

LOCAL_ACCOUNT_PREFIX = "LocalAccount"


def create_authenticator(auth_mode: str, **kwargs):
    """
    Factory function to create the appropriate authenticator.

    Args:
        auth_mode: Authentication mode ("auto-login", "dummy", "github", "multi")
        **kwargs: Additional configuration options

    Returns:
        Authenticator class (not instance)
    """
    if auth_mode == "auto-login":
        return AutoLoginAuthenticator
    elif auth_mode == "dummy":
        return "dummy"
    elif auth_mode == "github":
        return CustomGitHubOAuthenticator
    elif auth_mode == "multi":
        return CustomMultiAuthenticator
    else:
        print(f"[WARN] Unknown auth mode: {auth_mode}, falling back to dummy")
        return "dummy"


__all__ = [
    "RemoteLabAuthenticator",
    "AutoLoginAuthenticator",
    "CustomGitHubOAuthenticator",
    "CustomFirstUseAuthenticator",
    "CustomMultiAuthenticator",
    "create_authenticator",
    "LOCAL_ACCOUNT_PREFIX",
    "GITHUB_USERNAME_PREFIX",
]
