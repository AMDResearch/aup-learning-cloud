<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

# AUP Learning Cloud Code Images

This directory defines the generic browser coding environments for AUP Learning Cloud. They run `code-server` directly as the single-user process behind JupyterHub.

## Image Model

The coding environments are intentionally generic:

- `auplc-code-cpu` inherits from `ghcr.io/amdresearch/auplc-default:latest` for CPU-only development.
- `auplc-code-gpu` inherits from `ghcr.io/amdresearch/auplc-base:latest` for GPU-accelerated development.
- Existing `auplc-default`, `auplc-base`, and `Course-*` images remain notebook/course-focused.
- Course-specific VS Code image families are not part of this workflow.

The Code images are the shared developer-toolchain layer. Put browser editor,
Node.js, TypeScript/frontend, and native build tooling here instead of adding
those tools to Base notebook images or Course images. CPU and GPU Code images
are built from the same Dockerfile and differ only by `BASE_IMAGE`, so the Code
layer stays consistent across hardware targets.

The default Hub resource keys are `code-cpu` and `code-gpu`. Code-server launch behavior is configured through `custom.resources.metadata.<resource>.launchMode: code-server`, alongside the same `custom.resources.images`, `custom.resources.requirements`, `custom.resources.metadata.<resource>.defaultPath`, and `custom.teams.mapping` model as notebook resources in `runtime/values.yaml`.

## Build Commands

From the repository root:

```bash
make -C dockerfiles code-cpu
make -C dockerfiles code-gpu GPU_TARGET=gfx1151
make -C dockerfiles code
```

`code-cpu` builds `ghcr.io/amdresearch/auplc-code-cpu:latest`. `code-gpu` builds `ghcr.io/amdresearch/auplc-code-gpu:latest` and tags the selected GPU target, for example `ghcr.io/amdresearch/auplc-code-gpu:latest-gfx1151`. The aggregate `code` target builds both.

The Dockerfile pins code-server to version `4.96.4` so builds use a known editor runtime instead of silently changing when a new upstream release appears.

Additional build arguments customize the shared development toolchain:

- `NODE_IMAGE` selects the upstream Node.js image stage. The final image copies
  Node.js, `npm`, `npx`, `corepack`, and the bundled global Node modules from
  this stage instead of configuring a NodeSource or apt Node repository. The
  default is `docker.io/library/node:22-bookworm-slim`.
- `PNPM_VERSION` pins the `pnpm` version prepared through `corepack` and
  installed globally for runtime users. The default is `10.27.0`.
- `CODE_GLOBAL_NPM_PACKAGES` is a space-separated list of small global JS/TS
  tools installed into the Code image. The default is
  `typescript tsx vite eslint prettier`.
- `NPM_REGISTRY` configures the npm registry mirror for both the extension
  builder stage and the final Node toolchain install.
- `PIXI_VERSION` pins the Pixi binary installed into `/usr/local/bin`. The
  default is `v0.68.1`.
- `PIXI_DOWNLOAD_URL` overrides the Pixi binary URL, which is useful when the
  build environment must download Pixi from an approved mirror instead of
  GitHub releases.
- `PIXI_CONDA_FORGE_MIRROR` configures Pixi's conda-forge channel mirror. The
  default is Tsinghua TUNA's public mirror at
  `https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge`. Set this
  to an internal or regional mirror when required by local policy.

Common apt packages for the Code layer are listed in
`packages/code-common-apt.txt`. Keep package additions there so CPU and GPU Code
images continue to share one package set and the Dockerfile remains small.

## Runtime Behavior

The start script launches:

```bash
code-server --auth none --bind-addr 127.0.0.1:8889 --ignore-last-opened "${AUPLC_CODE_WORKDIR:-$(pwd)}"
nginx -c /tmp/auplc-code-server-nginx.conf -g 'daemon off;'
```

nginx listens on the public single-user port `8888`, strips the JupyterHub
service prefix such as `/user/<name>/`, and proxies HTTP/WebSocket traffic to
code-server on loopback. The proxy must preserve the full browser `Host` value
with `X-Forwarded-Host` so code-server's WebSocket origin check succeeds behind
JupyterHub and NodePort-style local URLs.

`defaultPath` is the initial landing path for a resource. The target path is
chosen in this order: Custom Repo clone path, resource `defaultPath`, then the
image or single-user application default, normally the image `WORKDIR`. Omitted
and `null` `defaultPath` values do not force a Hub landing override; empty
strings are invalid; `/` means land at the container root. This setting doesn't
limit what users can access. It only selects the first workspace shown by the
application.

Git, Node.js LTS, `npm`, `npx`, `corepack`, pinned `pnpm`, TypeScript/frontend
helpers, Pixi, and native build tools are installed in the image so cloned
projects can use source control, frontend workflows, sudo-free user package
management, and native npm package builds from the integrated terminal and
editor UI without additional setup.

The Code images also route user-level global npm installs into the persistent
home directory instead of `/usr/local`: `NPM_CONFIG_PREFIX` defaults to
`/home/jovyan/.local`, and `/home/jovyan/.local/bin` is prepended to `PATH`.
This lets users install small project CLIs with commands such as
`npm install -g cowsay` without sudo or write access to system directories.

For code-server's outgoing link protection, the Hub automatically injects the
current public Hub host into `AUPLC_CODE_TRUSTED_DOMAINS` so the built-in
Back-to-Hub action can open `/hub/home` without an external-site confirmation.
Deployments that intentionally open additional trusted sites can set
`custom.codeServer.extraTrustedDomains` to host/domain entries such as
`docs.example.edu`; do not include URL schemes or paths.

Pixi is provided as the sudo-free, apt-like package manager for user-space
native tools and project environments. The image writes `/etc/pixi/config.toml`
so requests for `https://conda.anaconda.org/conda-forge` are redirected to the
configured mirror and no direct upstream fallback is listed by default. Users can
create reproducible project environments with commands such as:

```bash
pixi init my-lab
cd my-lab
pixi add cmake pkg-config openssl zlib jq ripgrep
pixi run jq --version
```

Pixi remains a user-space package manager. It does not replace image rebuilds or
cluster administration for kernel modules, GPU/NPU drivers, device plugins,
udev rules, system services, or packages that must write to root-owned system
directories.

Extensions resolved from the Marketplace and local `.vsix` packages during the
image build are installed as root-owned system extensions under
`/usr/lib/code-server/lib/vscode/extensions`. User-installed extensions remain
in the persistent directory
`/home/jovyan/.local/share/code-server/extensions`.

Runtime startup does not install, copy, merge, stage, or lock extension data,
and it does not access an extension marketplace. Existing user data is left
untouched, including extension copies installed or seeded by earlier images.
When the system and user directories contain the same extension ID, native VS
Code extension precedence determines which copy is active.

`PORT` remains the nginx public-listen input, but the launcher removes it from
the code-server child environment before passing the explicit loopback
`--bind-addr`. This prevents code-server's environment precedence from binding
the nginx-facing public port.

`--auth none` is acceptable only because JupyterHub and the JupyterHub proxy remain the authentication boundary. The user pod's port `8888` must stay private to the Hub/proxy path and must not be exposed directly through an unauthenticated service, ingress, or port-forward shared with untrusted users.

When users provide a Git repository on the spawn form, the existing init-container clone flow is reused. For resources with `launchMode: code-server`, the spawner points `AUPLC_CODE_WORKDIR` at the cloned directory or explicit resource target path, and the launcher starts code-server with that folder so it opens the requested workspace. If neither Custom Repo nor `defaultPath` is set, the launcher opens the image `WORKDIR`. The launcher also passes `--ignore-last-opened` so a persisted previous workspace cannot override the requested folder.

A direct code-server URL with `?folder=<path>` works when the browser reaches
the proxied code-server root route. Hub spawn completion, however, redirects the
browser to the server base URL, and code-server doesn't consume
`JUPYTERHUB_DEFAULT_URL` by itself. AUPLC therefore keeps `AUPLC_CODE_WORKDIR` as
the reliable adapter between Hub resource selection and the code-server process.

Official Code images are checked by the resource contract verifier:

```bash
make -C dockerfiles verify-resource-contracts
```

The verifier checks official image metadata, image `WORKDIR`, path existence,
and the code-server launcher contract. Runtime spawning doesn't check path
existence for arbitrary or custom images. If a custom code image sets a
`defaultPath`, create that path in the image or code-server may show its own
landing error. If the image already declares the desired `WORKDIR`, omit
`defaultPath` to preserve it.

## Extensions

Default third-party extensions are listed in `extensions.txt`:

```text
ms-python.python
ms-toolsai.jupyter
redhat.vscode-yaml
eamodio.gitlens
ms-python.debugpy
charliermarsh.ruff
```

This baseline keeps Python and Jupyter support for course work, Debugpy for Python debugging, and Ruff for Python linting and formatting. YAML is retained so users can read and edit course, Kubernetes, and other configuration files without adding their own support first. GitLens is retained on purpose so researchers can learn Git history, blame, and commit discipline inside the same workspace they use for code.

Extension versions are not pinned in this iteration. During each image build,
code-server resolves the current compatible Marketplace releases and installs
them with local `.vsix` packages into the root-owned system extension directory.
Only the code-server package itself is pinned.

User-installed extensions are kept under the user's persistent home volume.
Image startup does not alter this directory. Copies installed by users or seeded
by earlier images remain in place, and native VS Code extension precedence
applies when a user copy and a system copy share an extension ID.

Default editor settings are also not baked into the image in this iteration. User workspaces and profiles should keep control over editor preferences.

Local `.vsix` packages from `extensions/` are installed during the image build. The AUPLC Back-to-Hub extension is packaged from `runtime/code-server/extensions/auplc-hub-link` inside the Dockerfile and then installed into the image; generated `.vsix` artifacts must not be committed. Before adding or redistributing additional VS Code, OpenVSX, or Marketplace extensions, verify that each extension's license and marketplace terms permit your intended use.

## Deployment Notes

After pushing or loading the code images, confirm `runtime/values.yaml` or the environment-specific override points `code-cpu` and `code-gpu` at the desired tags. For a Helm-managed deployment, render or upgrade with the same values files used by the target cluster, then restart Hub pods if only Hub code/config needs to reload.
