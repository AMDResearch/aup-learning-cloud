# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

SHELL := /bin/bash


# Export to K3s image dir: off by default. Set SAVE_IMAGES=1 and K3S_IMAGES_DIR to enable.
SAVE_IMAGES ?=
K3S_IMAGES_DIR ?= /var/lib/rancher/k3s/agent/images

# Mirror configuration (optional)
# MIRROR_PREFIX: Registry mirror prefix (e.g., mirror.example.com)
#   Transforms: quay.io/image -> mirror.example.com/quay.io/image
# MIRROR_PIP: PyPI mirror URL
# MIRROR_NPM: npm registry URL
MIRROR_PREFIX ?=
MIRROR_PIP ?=
MIRROR_NPM ?=

# GPU target architecture (short AMD apt-repo name; e.g. gfx110x, gfx1150,
# gfx1151, gfx120x). Dockerfile.rocm maps this to the corresponding pip
# wheel path (gfx110X-all / gfx120X-all for the RDNA 3 / RDNA 4 buckets).
GPU_TARGET ?= gfx1151

# GPU base image used by course Dockerfiles (override to track a specific version)
GPU_BASE_IMAGE ?= ghcr.io/amdresearch/auplc-base:latest

# vLLM image build knobs (consumed by dockerfiles/VLLM/build.sh).
# Override on the command line:
#   make vllm VLLM_REF=v0.10.0 MAX_JOBS=8
VLLM_REF ?=
VLLM_MAX_JOBS ?= 4
FLASH_ATTN_REF ?= main_perf

# Build args for docker build (constructed from mirror settings)
BUILD_ARGS :=
ifneq ($(MIRROR_PREFIX),)
  BUILD_ARGS += --build-arg NODE_IMAGE=$(MIRROR_PREFIX)/docker.io/library/node:20-alpine
  BUILD_ARGS += --build-arg HUB_IMAGE=$(MIRROR_PREFIX)/quay.io/jupyterhub/k8s-hub:4.3.3
endif
ifneq ($(MIRROR_PIP),)
  BUILD_ARGS += --build-arg PIP_INDEX_URL=$(MIRROR_PIP)
endif
ifneq ($(MIRROR_NPM),)
  BUILD_ARGS += --build-arg NPM_REGISTRY=$(MIRROR_NPM)
endif

.PHONY: all base base-cpu base-rocm base-gfx1151 hub courses cv dl llm physim vllm

# Build all images
all: base hub courses

# --- Base Images ---
base: base-cpu base-rocm

base-cpu:
	@echo "-------------------------------------------"; \
	 	echo "Building Base Image (cpu)..."; \
		echo "-------------------------------------------";

	cd Base && docker build $(BUILD_ARGS) \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/quay.io/jupyter/base-notebook:python-3.12,) \
		-t ghcr.io/amdresearch/auplc-default:latest --file Dockerfile.cpu .
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-default:latest

base-rocm:
	@echo "-------------------------------------------"; \
	 	echo "Building Base Image (rocm, GPU_TARGET=$(GPU_TARGET))..."; \
		echo "-------------------------------------------";

	cd Base && docker build $(BUILD_ARGS) \
		--build-arg GPU_TARGET=$(GPU_TARGET) \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/docker.io/library/ubuntu:24.04,) \
		-t ghcr.io/amdresearch/auplc-base:latest --file Dockerfile.rocm .
	docker tag ghcr.io/amdresearch/auplc-base:latest ghcr.io/amdresearch/auplc-base:latest-$(GPU_TARGET)

# Deprecated alias — use base-rocm instead
base-gfx1151: base-rocm

# --- Hub Image ---
hub:
	@echo "-------------------------------------------"; \
	 	echo "Building Hub Image..."; \
		echo "-------------------------------------------";

	cd Hub && NODE_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/docker.io/library/node:20-alpine,)" \
		HUB_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/quay.io/jupyterhub/k8s-hub:4.3.3,)" \
		PIP_INDEX_URL="$(MIRROR_PIP)" \
		NPM_REGISTRY="$(MIRROR_NPM)" \
		bash ./build.sh
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-hub:latest

# --- Course Images ---
courses: cv dl llm physim

cv:
	@echo "-------------------------------------------"; \
		echo "Building CV Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/CV && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-cv:latest ghcr.io/amdresearch/auplc-cv:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-cv:latest

dl:
	@echo "-------------------------------------------"; \
		echo "Building DL Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/DL && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-dl:latest ghcr.io/amdresearch/auplc-dl:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-dl:latest

llm:
	@echo "-------------------------------------------"; \
		echo "Building LLM Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/LLM && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-llm:latest ghcr.io/amdresearch/auplc-llm:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-llm:latest

physim:
	@echo "-------------------------------------------"; \
		echo "Building PhySim Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/PhySim && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-physim:latest ghcr.io/amdresearch/auplc-physim:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-physim:latest

# --- vLLM Base Image ---
# Builds vLLM + AITER flash-attention from source on top of auplc-base.
# Long build (~45-90 min on Strix Halo) — see dockerfiles/VLLM/README.md.
vllm:
	@echo "-------------------------------------------"; \
		echo "Building vLLM Image (GPU_TARGET=$(GPU_TARGET))..."; \
		echo "-------------------------------------------";

	cd VLLM && BASE_IMAGE=$(GPU_BASE_IMAGE) \
		GPU_TARGET=$(GPU_TARGET) \
		MAX_JOBS=$(VLLM_MAX_JOBS) \
		VLLM_REF=$(VLLM_REF) \
		FLASH_ATTN_REF=$(FLASH_ATTN_REF) \
		bash ./build.sh
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-vllm:latest

# --- Export Images ---
save-image:
	@if [ -n "$(SAVE_IMAGES)" ] && [ -n "$(K3S_IMAGES_DIR)" ]; then \
		echo "Exporting $(IMAGE) to $(K3S_IMAGES_DIR)..."; \
		filename=$$(basename $(IMAGE)); \
		filename=$$(echo $$filename | sed 's/:/-/g').tar; \
		out_path="$(K3S_IMAGES_DIR)/$$filename"; \
		echo "-------------------------------------------"; \
		echo "Export: $(IMAGE)"; \
		echo "Save to : $$out_path"; \
		sudo rm -f $$out_path; \
		sudo docker save "$(IMAGE)" -o "$$out_path" && echo "✅ Success" || (echo "❌ ERROR"; exit 1); \
		echo "-------------------------------------------"; \
	else \
		echo "Skipping export for $(IMAGE) (set SAVE_IMAGES=1 and K3S_IMAGES_DIR to enable)."; \
	fi
