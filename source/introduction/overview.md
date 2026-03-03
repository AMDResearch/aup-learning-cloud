# Overview

AUP Learning Cloud is a tailored JupyterHub deployment designed to provide an intuitive and hands-on AI learning experience. It features a comprehensive suite of AI toolkits running on AMD hardware acceleration, enabling users to learn and experiment with ease.

```{image} ../_static/images/software-stack.png
:alt: Software Architecture
:align: center
```

## What is AUP Learning Cloud?

AUP Learning Cloud provides a multi-user Jupyter notebook environment optimized for AI and machine learning education on AMD hardware platforms.

## Key Features

### Hardware Acceleration

- **AMD GPU**: Leverage ROCm for high-performance deep learning and AI workloads
- **AMD NPU**: Utilize Ryzen™ AI for efficient neural processing unit tasks
- **AMD CPU**: Support for general-purpose CPU-based computations

### Flexible Deployment

Kubernetes provides a robust infrastructure for deploying and managing JupyterHub. We support both single-node and multi-node K3s cluster deployments.

### Custom URL Launcher

We provide a basic **ROCm + PyTorch** environment; you can clone your own Git repository into this environment at server start (via URL and branch or by selecting a repo from your GitHub account). Your code is then available in the workspace so you can run it immediately.

### Authentication

Seamless integration with GitHub Single Sign-On (SSO) and Native Authenticator for secure and efficient user authentication:

- **Auto-admin on install**: Initial admin created automatically with random password
- **Dual login**: GitHub OAuth + Native accounts on single login page
- **Batch user management**: CSV/Excel-based bulk operations via scripts

### Storage Management and Security

Dynamic NFS provisioning ensures scalable and persistent storage for user data, while end-to-end TLS encryption with automated certificate management guarantees secure and reliable communication.

## Learning Solutions

AUP Learning Cloud offers the following Learning Toolkits:

:::{note}
Only **Deep Learning** and **Large Language Model from Scratch** are available in the v1.0 release.
:::

- **Computer Vision** - 10 hands-on labs covering common computer vision concepts and techniques
- **Deep Learning** - 12 hands-on labs covering common deep learning concepts and techniques
- **Large Language Model from Scratch** - 9 hands-on labs designed to teach LLM development from scratch

## Available Notebook Environments

| Environment | Image | Version | Hardware |
|------------|-------|---------|----------|
| Base CPU | `ghcr.io/amdresearch/auplc-default` | v1.0 | CPU |
| CV COURSE | `ghcr.io/amdresearch/auplc-cv` | v1.0 | GPU (Strix-Halo) |
| DL COURSE | `ghcr.io/amdresearch/auplc-dl` | v1.0 | GPU (Strix-Halo) |
| LLM COURSE | `ghcr.io/amdresearch/auplc-llm` | v1.0 | GPU (Strix-Halo) |
