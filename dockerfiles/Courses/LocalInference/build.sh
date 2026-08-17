#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

cp -r ../../../projects/LocalInference ./course_data
trap 'rm -rf course_data' EXIT

# Without Export HF_TOKEN the build falls since the arg is empty by
# default the Dockerfile.
docker build ${BASE_IMAGE:+--build-arg BASE_IMAGE="$BASE_IMAGE"} \
  ${HF_TOKEN:+--secret id=hf_token,env=HF_TOKEN} \
  -t ghcr.io/amdresearch/auplc-localinference:latest .
