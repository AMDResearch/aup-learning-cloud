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

# Global build arguments
ARG NODE_IMAGE=node:20-alpine
ARG HUB_IMAGE=quay.io/jupyterhub/k8s-hub:4.3.3
ARG NPM_REGISTRY=
ARG PIP_INDEX_URL=

# Stage 1: Build frontend (monorepo)
FROM ${NODE_IMAGE} AS frontend-builder
ARG NPM_REGISTRY

WORKDIR /build/runtime

RUN if [ -n "${NPM_REGISTRY}" ]; then npm config set registry "${NPM_REGISTRY}"; fi
RUN npm install -g pnpm@10.27.0
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi

# Copy monorepo configuration and lockfile
COPY runtime/package.json runtime/pnpm-workspace.yaml runtime/pnpm-lock.yaml runtime/.npmrc ./
COPY runtime/hub/frontend/tsconfig.base.json ./hub/frontend/tsconfig.base.json

# Copy package.json files for dependency installation
COPY runtime/hub/frontend/packages/shared/package.json ./hub/frontend/packages/shared/
COPY runtime/hub/frontend/packages/login-css/package.json ./hub/frontend/packages/login-css/
COPY runtime/hub/frontend/apps/admin/package.json ./hub/frontend/apps/admin/
COPY runtime/hub/frontend/apps/spawn/package.json ./hub/frontend/apps/spawn/
COPY runtime/hub/frontend/apps/home/package.json ./hub/frontend/apps/home/

# Install only the Hub frontend targets and their workspace dependencies.
RUN pnpm install --frozen-lockfile --prod=false \
    --filter './hub/frontend/apps/**...' \
    --filter './hub/frontend/packages/login-css...'

# Copy source code
COPY runtime/hub/frontend/packages/ ./hub/frontend/packages/
COPY runtime/hub/frontend/apps/ ./hub/frontend/apps/

# Templates are scanned by @auplc/login-css for Tailwind class usage, so
# they must be present at /app/templates/ during the build. The final
# image still copies them fresh from the repo into /tmp/custom_templates.
COPY runtime/hub/frontend/templates/ ./hub/frontend/templates/

# Build only Hub frontend targets. Notebook JupyterLab extensions are built in
# notebook base images where Python/JupyterLab are available.
RUN pnpm -r --filter './hub/frontend/apps/**...' --filter './hub/frontend/packages/login-css...' run build

# Stage 2: Final Hub image
FROM ${HUB_IMAGE}
ARG PIP_INDEX_URL

USER root

# Frontend: templates and static files
RUN mkdir -p /tmp/custom_templates/static/css /tmp/custom_templates/static/js \
    /usr/local/share/jupyterhub/static/admin-ui \
    /usr/local/share/jupyterhub/static/spawn-ui \
    /usr/local/share/jupyterhub/static/home-ui \
    /usr/local/share/jupyterhub/static/css

COPY --chmod=644 runtime/hub/frontend/templates/ /tmp/custom_templates/
COPY --from=frontend-builder /build/runtime/hub/frontend/apps/admin/dist/ /usr/local/share/jupyterhub/static/admin-ui/
COPY --from=frontend-builder /build/runtime/hub/frontend/apps/spawn/dist/ /usr/local/share/jupyterhub/static/spawn-ui/
COPY --from=frontend-builder /build/runtime/hub/frontend/apps/home/dist/ /usr/local/share/jupyterhub/static/home-ui/
# Same-origin Tailwind CSS for the login Jinja template; replaces the
# previous cdn.tailwindcss.com script reference.
COPY --chmod=644 --from=frontend-builder /build/runtime/hub/frontend/packages/login-css/dist/login.min.css \
    /usr/local/share/jupyterhub/static/css/login.min.css
RUN chown -R 1000:1000 /usr/local/share/jupyterhub/static/admin-ui/ \
    /usr/local/share/jupyterhub/static/spawn-ui/ \
    /usr/local/share/jupyterhub/static/home-ui/ \
    /usr/local/share/jupyterhub/static/css/login.min.css

# Backend: Python dependencies and core logic
RUN pip install --no-cache-dir uv

COPY runtime/hub/requirements.txt /tmp/requirements.txt
RUN if [ -n "${PIP_INDEX_URL}" ]; then \
        uv pip install --system --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt; \
    else \
        uv pip install --system -r /tmp/requirements.txt; \
    fi

COPY runtime/hub/core/ /usr/local/lib/core/
RUN chown -R 1000:1000 /usr/local/lib/core/ && \
    find /usr/local/lib/core/ -type d -exec chmod 755 {} \; && \
    find /usr/local/lib/core/ -type f -exec chmod 644 {} \;

ENV PYTHONPATH="/usr/local/lib"

# Finalize
USER jovyan
ENV JUPYTERHUB_TEMPLATE_PATH=/tmp/custom_templates

RUN ls -la /tmp/custom_templates && \
    ls -la /usr/local/share/jupyterhub/static/admin-ui/ && \
    ls -la /usr/local/share/jupyterhub/static/spawn-ui/ && \
    ls -la /usr/local/share/jupyterhub/static/home-ui/ && \
    ls -la /usr/local/share/jupyterhub/static/css/login.min.css
