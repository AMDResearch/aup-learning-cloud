#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

cp -r ../../../projects/LocalInference ./course_data
trap 'rm -rf course_data' EXIT

docker build ${BASE_IMAGE:+--build-arg BASE_IMAGE="$BASE_IMAGE"} \
  -t ghcr.io/amdresearch/auplc-localinference:latest .
