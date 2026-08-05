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

from typing import Any

from core.authenticators.auto_login import AutoLoginAuthenticator
from core.authenticators.firstuse import CustomFirstUseAuthenticator
from core.authenticators.github_app import GITHUB_USERNAME_PREFIX, CustomGitHubOAuthenticator
from core.authenticators.jwt import RemoteLabAuthenticator
from core.authenticators.multi import CustomMultiAuthenticator
from core.config import AuthCapabilities, AuthConfigurationError

LOCAL_ACCOUNT_PREFIX = "LocalAccount"


def configure_authenticator(c: Any, auth: AuthCapabilities) -> None:
    """Configure the JupyterHub authenticator for validated capabilities."""

    match auth:
        case AuthCapabilities(auto_login=True, dummy=False, native=False, github=False):
            c.JupyterHub.authenticator_class = AutoLoginAuthenticator
            c.Authenticator.allow_all = True
        case AuthCapabilities(auto_login=False, dummy=True, native=False, github=False):
            c.JupyterHub.authenticator_class = "dummy"
            c.Authenticator.allow_all = True
        case AuthCapabilities(auto_login=False, dummy=False, native=True, github=False):
            c.JupyterHub.authenticator_class = CustomFirstUseAuthenticator
            c.Authenticator.allow_all = True
        case AuthCapabilities(auto_login=False, dummy=False, native=False, github=True):
            c.JupyterHub.authenticator_class = CustomGitHubOAuthenticator
            c.GitHubOAuthenticator.allow_all = False
        case AuthCapabilities(auto_login=False, dummy=False, native=True, github=True):
            c.JupyterHub.authenticator_class = CustomMultiAuthenticator
            c.GitHubOAuthenticator.allow_all = False
            c.MultiAuthenticator.allow_all = True
            c.MultiAuthenticator.authenticators = [
                {"authenticator_class": CustomGitHubOAuthenticator, "url_prefix": "/github"},
                {
                    "authenticator_class": CustomFirstUseAuthenticator,
                    "url_prefix": "/native",
                    "config": {"prefix": "", "allow_all": True},
                },
            ]
        case AuthCapabilities():
            raise AuthConfigurationError("auth must enable one exclusive provider or native + github")
        case unsupported:
            raise AuthConfigurationError(
                f"authentication capabilities must be AuthCapabilities, got {type(unsupported).__name__}"
            )


__all__ = [
    "RemoteLabAuthenticator",
    "AutoLoginAuthenticator",
    "CustomGitHubOAuthenticator",
    "CustomFirstUseAuthenticator",
    "CustomMultiAuthenticator",
    "configure_authenticator",
    "LOCAL_ACCOUNT_PREFIX",
    "GITHUB_USERNAME_PREFIX",
]
