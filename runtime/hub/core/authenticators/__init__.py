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
from core.config import AuthCapabilities, AuthConfigurationError, LegacyAuthMode

LOCAL_ACCOUNT_PREFIX = "LocalAccount"


def create_authenticator(auth: AuthCapabilities | LegacyAuthMode) -> type | str:
    """Select the JupyterHub authenticator class for validated capabilities."""

    match auth:
        case AuthCapabilities(auto_login=True, dummy=False, native=False, github=False) | "auto-login":
            return AutoLoginAuthenticator
        case AuthCapabilities(auto_login=False, dummy=True, native=False, github=False) | "dummy":
            return "dummy"
        case AuthCapabilities(auto_login=False, dummy=False, native=True, github=False) | "local":
            return CustomFirstUseAuthenticator
        case AuthCapabilities(auto_login=False, dummy=False, native=False, github=True) | "github":
            return CustomGitHubOAuthenticator
        case AuthCapabilities(auto_login=False, dummy=False, native=True, github=True) | "multi":
            return CustomMultiAuthenticator
        case AuthCapabilities():
            raise AuthConfigurationError("auth must enable one exclusive provider or native + github")
        # Todo 13: remove the effective-mode compatibility boundary after Todo 6 consumes config.auth.
        case str():
            raise ValueError(f"Unknown authentication mode: {auth}")
        case bool():
            raise AuthConfigurationError("authentication capabilities cannot be boolean values")
        case unsupported:
            raise AuthConfigurationError(
                f"authentication capabilities must be AuthCapabilities or a supported effective mode, got {type(unsupported).__name__}"
            )


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
