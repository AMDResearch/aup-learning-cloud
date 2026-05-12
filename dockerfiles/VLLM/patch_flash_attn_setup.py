#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
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
#
# ----------------------------------------------------------------------------
# Strip the in-tree AITER rebuild from ROCm/flash-attention's setup.py.
#
# We pip-install AITER from a separate build step (see the Dockerfile), so the
# flash-attention setup.py — which otherwise runs `pip wheel third_party/aiter`
# as a subprocess at install time — would re-fetch CK and re-compile every
# kernel from scratch, slowly and against build deps we don't necessarily
# have.
# ----------------------------------------------------------------------------

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "setup.py")
    if not target.exists():
        print(f"[patch_flash_attn_setup] {target} not found", file=sys.stderr)
        return 1

    src = target.read_text()
    patched = re.sub(
        r"subprocess\.run\([\s\S]*?third_party/aiter[\s\S]*?check=True,\s*\)",
        "pass  # patched: aiter installed separately from prebuilt wheel",
        src,
    )
    if patched == src:
        print(f"[patch_flash_attn_setup] no AITER subprocess.run block found in {target} (already patched?)")
        return 0
    target.write_text(patched)
    print(f"[patch_flash_attn_setup] patched {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
