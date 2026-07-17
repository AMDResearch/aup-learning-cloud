# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

ARG NODE_IMAGE=docker.io/library/node:22-bookworm-slim
ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-default:latest
ARG IMAGE_FLAVOR=cpu
ARG CODE_SERVER_VERSION=4.96.4

FROM ${NODE_IMAGE} AS node-runtime

FROM node-runtime AS hub-link-builder

ARG NPM_REGISTRY=
ARG PNPM_VERSION=10.27.0
WORKDIR /build/runtime

RUN npm install -g pnpm@${PNPM_VERSION}
COPY runtime/package.json runtime/pnpm-workspace.yaml runtime/pnpm-lock.yaml runtime/.npmrc ./
COPY runtime/hub/frontend/tsconfig.base.json ./hub/frontend/tsconfig.base.json
COPY runtime/shared/runtime-status ./shared/runtime-status
COPY runtime/code-server/extensions/auplc-hub-link ./code-server/extensions/auplc-hub-link
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi && \
    pnpm install --frozen-lockfile --prod=false --filter auplc-hub-link...
RUN pnpm --filter @auplc/runtime-status run build && \
    pnpm --filter auplc-hub-link run build && \
    test -f code-server/extensions/auplc-hub-link/auplc-hub-link-0.0.1.vsix

FROM ${BASE_IMAGE}

ARG CODE_SERVER_VERSION=4.96.4
ARG IMAGE_FLAVOR
ARG NPM_REGISTRY=
ARG PNPM_VERSION=10.27.0
ARG CODE_GLOBAL_NPM_PACKAGES
ARG PIXI_VERSION=v0.68.1
ARG PIXI_DOWNLOAD_URL=
ARG PIXI_CONDA_FORGE_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
USER root

COPY dockerfiles/Code/packages/code-common-apt.txt /opt/auplc/build/code-common-apt.txt
COPY dockerfiles/Code/scripts/install-code-system-packages.sh dockerfiles/Code/scripts/install-node-toolchain.sh dockerfiles/Code/scripts/install-pixi-toolchain.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/install-code-system-packages.sh /usr/local/bin/install-node-toolchain.sh /usr/local/bin/install-pixi-toolchain.sh && \
    /usr/local/bin/install-code-system-packages.sh /opt/auplc/build/code-common-apt.txt

RUN /usr/local/bin/install-pixi-toolchain.sh

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack

RUN /usr/local/bin/install-node-toolchain.sh

ENV NPM_CONFIG_PREFIX=/home/jovyan/.local
ENV PIXI_HOME=/home/jovyan/.pixi
ENV PATH=/home/jovyan/.local/bin:/home/jovyan/.pixi/bin:${PATH}

COPY dockerfiles/Code/extensions.txt /opt/auplc/extensions/extensions.txt
COPY dockerfiles/Code/extensions/ /opt/auplc/extensions/local/
COPY --from=hub-link-builder /build/runtime/code-server/extensions/auplc-hub-link/auplc-hub-link-0.0.1.vsix /opt/auplc/extensions/local/auplc-hub-link-0.0.1.vsix
COPY dockerfiles/Code/start-code-server.sh /usr/local/bin/start-code-server.sh

RUN chmod +x /usr/local/bin/start-code-server.sh && \
    mkdir -p \
        /opt/auplc/extensions/local \
        /opt/auplc/code-server/extensions \
        /home/jovyan/.cache \
        /home/jovyan/.config \
        /home/jovyan/.local/bin \
        /home/jovyan/.local/share/code-server \
        /home/jovyan/.pixi/bin \
        /home/jovyan/.npm && \
    chown -R jovyan:100 /opt/auplc /home/jovyan/.cache /home/jovyan/.config /home/jovyan/.local /home/jovyan/.pixi /home/jovyan/.npm

USER jovyan

RUN set -eu; \
    while IFS= read -r extension_id || [ -n "${extension_id}" ]; do \
        case "${extension_id}" in ''|'#'*) continue ;; esac; \
        code-server --extensions-dir /opt/auplc/code-server/extensions --install-extension "${extension_id}"; \
    done < /opt/auplc/extensions/extensions.txt; \
    find /opt/auplc/extensions/local -type f -name '*.vsix' -print0 | \
        xargs -0 -r -n 1 code-server --extensions-dir /opt/auplc/code-server/extensions --install-extension

EXPOSE 8888
WORKDIR /home/jovyan
CMD ["/usr/local/bin/start-code-server.sh"]
