# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

SHELL := /bin/bash

K3S_IMAGES_DIR ?= /var/lib/rancher/k3s/agent/images

# Mirror configuration (optional)
# MIRROR_PREFIX: Registry mirror prefix (e.g., mirror.example.com)
#   Transforms: quay.io/image -> mirror.example.com/quay.io/image
# MIRROR_PIP: PyPI mirror URL
# MIRROR_NPM: npm registry URL
MIRROR_PREFIX ?=
MIRROR_PIP ?=
MIRROR_NPM ?=

# GPU base image used by course Dockerfiles (override to track a specific version)
GPU_BASE_IMAGE ?= ghcr.io/amdresearch/base-gfx1151:v0.1-full

# Build args for docker build (constructed from mirror settings)
BUILD_ARGS :=
ifneq ($(MIRROR_PREFIX),)
  BUILD_ARGS += --build-arg NODE_IMAGE=$(MIRROR_PREFIX)/docker.io/library/node:20-alpine
  BUILD_ARGS += --build-arg HUB_IMAGE=$(MIRROR_PREFIX)/quay.io/jupyterhub/k8s-hub:4.1.0
endif
ifneq ($(MIRROR_PIP),)
  BUILD_ARGS += --build-arg PIP_INDEX_URL=$(MIRROR_PIP)
endif
ifneq ($(MIRROR_NPM),)
  BUILD_ARGS += --build-arg NPM_REGISTRY=$(MIRROR_NPM)
endif

.PHONY: all base base-cpu base-gfx1151 hub courses cv dl llm physim

# Build all images
all: base hub courses

# --- Base Images ---
base: base-cpu base-gfx1151

base-cpu:
	@echo "-------------------------------------------"; \
	 	echo "Building Base Image (cpu)..."; \
		echo "-------------------------------------------";

	cd Base && docker build $(BUILD_ARGS) \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/quay.io/jupyter/base-notebook,) \
		-t ghcr.io/amdresearch/auplc-default:latest --file Dockerfile.cpu .
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-default:latest

base-gfx1151:
	@echo "-------------------------------------------"; \
	 	echo "Building Base Image (gfx1151)..."; \
		echo "-------------------------------------------";

	cd Base && docker build $(BUILD_ARGS) \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/docker.io/library/ubuntu:24.04,) \
		-t ghcr.io/amdresearch/base-gfx1151:v0.1-full --file Dockerfile.gfx1151 .

# --- Hub Image ---
hub:
	@echo "-------------------------------------------"; \
	 	echo "Building Hub Image..."; \
		echo "-------------------------------------------";

	cd Hub && NODE_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/docker.io/library/node:20-alpine,)" \
		HUB_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/quay.io/jupyterhub/k8s-hub:4.1.0,)" \
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
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-cv:latest

dl:
	@echo "-------------------------------------------"; \
		echo "Building DL Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/DL && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-dl:latest

llm:
	@echo "-------------------------------------------"; \
		echo "Building LLM Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/LLM && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-llm:latest

physim:
	@echo "-------------------------------------------"; \
		echo "Building PhySim Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/PhySim && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-physim:latest

# --- Export Images ---
save-image:
	@if [ -n "$(K3S_IMAGES_DIR)" ]; then \
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
		echo "K3S_IMAGES_DIR not set. Skipping export for $(IMAGE)."; \
	fi
