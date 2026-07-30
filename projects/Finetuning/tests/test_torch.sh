#!/bin/bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -e

echo "Testing ROCm torch environment..."

python3 - <<'PY'
import sys
import torch

print(f"torch            : {torch.__version__}")
print(f"torch.version.hip: {torch.version.hip}")
if not torch.version.hip:
    print("FAIL: torch is not a ROCm build.", file=sys.stderr)
    sys.exit(1)
if not torch.cuda.is_available():
    print("FAIL: no ROCm device visible. Check --device=/dev/kfd, /dev/dri.", file=sys.stderr)
    sys.exit(1)

print(f"device[0]        : {torch.cuda.get_device_name(0)}")
a = torch.randn(512, 512, device="cuda")
b = torch.randn(512, 512, device="cuda")
print(f"matmul ok        : sum={(a @ b).sum().item():.3f}")
print("PASS: ROCm torch env OK")
PY
