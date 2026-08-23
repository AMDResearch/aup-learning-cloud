# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Geometry helpers available to the cube-restack policy."""

import numpy as np


def offset(position, *, x=0.0, z=0.0):
    target = position.copy()
    target[0] += x
    target[2] += z
    return target


def stack_center(base_position, base_extent, object_extent):
    target = base_position.copy()
    target[2] += (base_extent[2] + object_extent[2]) / 2
    return target


DOWNWARD_QUATERNION = np.array([0.0, 0.0, 1.0, 0.0])
