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

import re
from urllib.parse import urlparse, urlunparse


def validate_and_sanitize_repo_url(url: str, allowed_providers: list[str]) -> tuple[bool, str, str]:
    if not url or not str(url).strip():
        return True, "", ""

    url = str(url).strip()
    if "://" not in url:
        url = "https://" + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return False, "Only HTTP/HTTPS URLs supported", ""
        if not parsed.netloc:
            return False, "Invalid URL format", ""

        path = parsed.path
        tree_match = re.match(r"^(/[^/]+/[^/]+)/tree/.+$", path)
        if tree_match:
            path = tree_match.group(1)
        if path.endswith(".git"):
            path = path[:-4]

        sanitized = urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))
        hostname = parsed.netloc.lower()
        if not any(hostname == provider or hostname.endswith("." + provider) for provider in allowed_providers):
            return False, f"Repository host '{hostname}' not authorized", ""
    except Exception as e:
        return False, f"URL parsing error: {e}", ""

    dangerous_patterns = [";", "||", "&&", "$(", "`", "\n", "\r"]
    if any(pat in sanitized for pat in dangerous_patterns):
        return False, "URL contains suspicious characters", ""

    return True, "", sanitized
