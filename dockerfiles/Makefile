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

# Image profiles and their tag suffixes come from the canonical ROCm catalog.
ROCM_PROFILE_RESOLVER := Base/rocm-targets.py
DEFAULT_AUP_IMAGE_PROFILE := $(shell python3 $(ROCM_PROFILE_RESOLVER) resolve-profile --format lines | awk -F= '$$1 == "PROFILE" { print $$2 }')
ifeq ($(strip $(AUP_IMAGE_PROFILE)),)
override AUP_IMAGE_PROFILE := $(DEFAULT_AUP_IMAGE_PROFILE)
endif
PROFILE_TAG_SUFFIX := $(shell python3 $(ROCM_PROFILE_RESOLVER) resolve-profile "$(AUP_IMAGE_PROFILE)" --format lines | awk -F= '$$1 == "TAG_SUFFIX" { print $$2 }')

# GPU base image used by course Dockerfiles (override to track a specific version)
GPU_BASE_IMAGE ?= ghcr.io/amdresearch/auplc-base:latest-$(PROFILE_TAG_SUFFIX)
CODE_GPU_BASE_IMAGE ?= ghcr.io/amdresearch/auplc-base:latest-$(PROFILE_TAG_SUFFIX)

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

.PHONY: all base base-cpu base-rocm hub code code-cpu code-gpu courses cv dl llm physim verify-resource-contracts

# Build all images
all: base hub code courses

verify-resource-contracts:
	python3 ../scripts/verify-resource-contracts.py

# --- Base Images ---
base: base-cpu base-rocm

base-cpu:
	@echo "-------------------------------------------"; \
	 	echo "Building Base Image (cpu)..."; \
		echo "-------------------------------------------";

	docker build $(BUILD_ARGS) \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/quay.io/jupyter/base-notebook:python-3.12,) \
		-t ghcr.io/amdresearch/auplc-default:latest --file Base/Dockerfile.cpu ..
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-default:latest

base-rocm:
	@echo "-------------------------------------------"; \
		echo "Building Base Image (rocm, AUP_IMAGE_PROFILE=$(AUP_IMAGE_PROFILE))..."; \
		echo "-------------------------------------------";

	docker build $(BUILD_ARGS) \
		--build-arg AUP_IMAGE_PROFILE="$(AUP_IMAGE_PROFILE)" \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/docker.io/library/ubuntu:24.04,) \
		-t ghcr.io/amdresearch/auplc-base:latest-$(PROFILE_TAG_SUFFIX) --file Base/Dockerfile.rocm ..
	if [ "$(AUP_IMAGE_PROFILE)" = "$(DEFAULT_AUP_IMAGE_PROFILE)" ]; then \
		docker tag ghcr.io/amdresearch/auplc-base:latest-$(PROFILE_TAG_SUFFIX) ghcr.io/amdresearch/auplc-base:latest; \
	fi
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-base:latest-$(PROFILE_TAG_SUFFIX)

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

# --- Code Images ---
code: code-cpu code-gpu

code-cpu:
	@echo "-------------------------------------------"; \
		echo "Building Code CPU Image..."; \
		echo "-------------------------------------------";

	cd Code && IMAGE_FLAVOR=cpu \
		BASE_IMAGE=ghcr.io/amdresearch/auplc-default:latest \
		NODE_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/docker.io/library/node:22-bookworm-slim,)" \
		NPM_REGISTRY="$(MIRROR_NPM)" \
		bash ./build.sh
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-code-cpu:latest

code-gpu:
	@echo "-------------------------------------------"; \
		echo "Building Code GPU Image (AUP_IMAGE_PROFILE=$(AUP_IMAGE_PROFILE))..."; \
		echo "-------------------------------------------";

	cd Code && IMAGE_FLAVOR=gpu \
		BASE_IMAGE="$(CODE_GPU_BASE_IMAGE)" \
		NODE_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/docker.io/library/node:22-bookworm-slim,)" \
		NPM_REGISTRY="$(MIRROR_NPM)" \
		bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-code-gpu:latest ghcr.io/amdresearch/auplc-code-gpu:latest-$(PROFILE_TAG_SUFFIX)
	if [ "$(AUP_IMAGE_PROFILE)" != "$(DEFAULT_AUP_IMAGE_PROFILE)" ]; then docker image rm ghcr.io/amdresearch/auplc-code-gpu:latest; fi
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-code-gpu:latest-$(PROFILE_TAG_SUFFIX)

# --- Course Images ---
courses: cv dl llm physim

cv:
	@echo "-------------------------------------------"; \
		echo "Building CV Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/CV && BASE_IMAGE="$(GPU_BASE_IMAGE)" bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-cv:latest ghcr.io/amdresearch/auplc-cv:latest-$(PROFILE_TAG_SUFFIX)
	if [ "$(AUP_IMAGE_PROFILE)" != "$(DEFAULT_AUP_IMAGE_PROFILE)" ]; then docker image rm ghcr.io/amdresearch/auplc-cv:latest; fi
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-cv:latest-$(PROFILE_TAG_SUFFIX)

dl:
	@echo "-------------------------------------------"; \
		echo "Building DL Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/DL && BASE_IMAGE="$(GPU_BASE_IMAGE)" bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-dl:latest ghcr.io/amdresearch/auplc-dl:latest-$(PROFILE_TAG_SUFFIX)
	if [ "$(AUP_IMAGE_PROFILE)" != "$(DEFAULT_AUP_IMAGE_PROFILE)" ]; then docker image rm ghcr.io/amdresearch/auplc-dl:latest; fi
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-dl:latest-$(PROFILE_TAG_SUFFIX)

llm:
	@echo "-------------------------------------------"; \
		echo "Building LLM Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/LLM && BASE_IMAGE="$(GPU_BASE_IMAGE)" bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-llm:latest ghcr.io/amdresearch/auplc-llm:latest-$(PROFILE_TAG_SUFFIX)
	if [ "$(AUP_IMAGE_PROFILE)" != "$(DEFAULT_AUP_IMAGE_PROFILE)" ]; then docker image rm ghcr.io/amdresearch/auplc-llm:latest; fi
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-llm:latest-$(PROFILE_TAG_SUFFIX)

physim:
	@echo "-------------------------------------------"; \
		echo "Building PhySim Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/PhySim && BASE_IMAGE="$(GPU_BASE_IMAGE)" bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-physim:latest ghcr.io/amdresearch/auplc-physim:latest-$(PROFILE_TAG_SUFFIX)
	if [ "$(AUP_IMAGE_PROFILE)" != "$(DEFAULT_AUP_IMAGE_PROFILE)" ]; then docker image rm ghcr.io/amdresearch/auplc-physim:latest; fi
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-physim:latest-$(PROFILE_TAG_SUFFIX)

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
