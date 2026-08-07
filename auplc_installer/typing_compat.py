# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

from typing import NoReturn


def assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(f"Expected unreachable value: {value!r}")
