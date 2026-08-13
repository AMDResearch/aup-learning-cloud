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
# gfx1151, gfx1152, gfx120x). Dockerfile.rocm maps this to the corresponding pip
# wheel path (gfx110X-all / gfx120X-all for the RDNA 3 / RDNA 4 buckets).
GPU_TARGET ?= gfx1151

ROCM_SDK_TARGET ?= $(GPU_TARGET)

# GPU base image used by course Dockerfiles (override to track a specific version)
GPU_BASE_IMAGE ?= ghcr.io/amdresearch/auplc-base:latest
CODE_GPU_BASE_IMAGE ?= ghcr.io/amdresearch/auplc-base:latest-$(GPU_TARGET)

# Finetuning course assets. ASSETS_SRC points at the RAW split-tar workshop bundle (base/ libero/
# tokenizer/ droid_dataset/ ft_checkpoint/). `make finetuning ASSETS_SRC=<bundle>` is FULLY
# self-contained: the Docker build itself unpacks the bundle and reconstructs the reference
# checkpoint (no host pre-stage), then bakes everything in so the image needs no shared mount.
# Set ASSETS_SRC= (empty) to build a code-only image for CI/registry.
ASSETS_ROOT      ?= /opt/auplc-assets
ASSETS_BUNDLE    ?= $(ASSETS_ROOT)/mm2_workshop_assets
ASSETS_SRC       ?= $(ASSETS_BUNDLE)
FINETUNING_IMAGE ?= ghcr.io/amdresearch/auplc-finetuning:latest

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

.PHONY: all base base-cpu base-rocm base-gfx1151 hub code code-cpu code-gpu courses cv dl llm physim finetuning local-inference verify-resource-contracts

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
	 	echo "Building Base Image (rocm, GPU_TARGET=$(GPU_TARGET))..."; \
		echo "-------------------------------------------";

	docker build $(BUILD_ARGS) \
		--build-arg GPU_TARGET=$(GPU_TARGET) \
		--build-arg ROCM_SDK_TARGET=$(ROCM_SDK_TARGET) \
		$(if $(MIRROR_PREFIX),--build-arg BASE_IMAGE=$(MIRROR_PREFIX)/docker.io/library/ubuntu:24.04,) \
		-t ghcr.io/amdresearch/auplc-base:latest --file Base/Dockerfile.rocm ..
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
		echo "Building Code GPU Image (GPU_TARGET=$(GPU_TARGET))..."; \
		echo "-------------------------------------------";

	cd Code && IMAGE_FLAVOR=gpu \
		BASE_IMAGE=$(CODE_GPU_BASE_IMAGE) \
		NODE_IMAGE="$(if $(MIRROR_PREFIX),$(MIRROR_PREFIX)/docker.io/library/node:22-bookworm-slim,)" \
		NPM_REGISTRY="$(MIRROR_NPM)" \
		bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-code-gpu:latest ghcr.io/amdresearch/auplc-code-gpu:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-code-gpu:latest

# --- Course Images ---
courses: cv dl llm physim finetuning local-inference

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

finetuning:
	@echo "-------------------------------------------"; \
		echo "Building ROSCon Finetuning Course Image (self-contained)..."; \
		echo "  pass the RAW workshop bundle via ASSETS_SRC, e.g.:"; \
		echo "  make -C dockerfiles finetuning GPU_TARGET=$(GPU_TARGET) ASSETS_SRC=/path/to/mm2_workshop_assets"; \
		echo "  (current ASSETS_SRC=$(ASSETS_SRC))"; \
		echo "-------------------------------------------";

	cd Courses/Finetuning && BASE_IMAGE=$(GPU_BASE_IMAGE) ASSETS_SRC="$(ASSETS_SRC)" bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-finetuning:latest ghcr.io/amdresearch/auplc-finetuning:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-finetuning:latest

# Back-compat alias. Pre-staging now happens INSIDE the Docker build, so this is equivalent to
# `make finetuning ASSETS_SRC=<bundle>`. Kept so existing docs / muscle-memory keep working.
.PHONY: finetuning-baked
finetuning-baked:
	@echo ">> 'finetuning-baked' now just runs 'finetuning' (bundle is pre-staged inside the build)."
	$(MAKE) finetuning ASSETS_SRC="$(ASSETS_SRC)"

local-inference:
	@echo "-------------------------------------------"; \
		echo "Building ROSCon Local Inference Course Image..."; \
		echo "-------------------------------------------";

	cd Courses/LocalInference && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-localinference:latest ghcr.io/amdresearch/auplc-localinference:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-localinference:latest

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
