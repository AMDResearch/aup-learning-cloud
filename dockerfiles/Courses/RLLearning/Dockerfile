# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

USER root
RUN mkdir -p /ryzers/notebooks

# The build script stages projects/RLLearning as course_data.
COPY ./course_data /ryzers/notebooks
RUN chown -R jovyan:100 /ryzers

USER jovyan
WORKDIR /ryzers/notebooks
