#!/bin/sh
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

# Git repository clone script for JupyterHub init container.
#
# Clones a repository onto the user's home PVC. The clone directory is
# cleaned up by a preStop lifecycle hook when the session ends, so the
# repository does not persist between sessions.
#
# Environment variables (required):
#   REPO_URL          - HTTPS URL of the git repository to clone
#   CLONE_DIR         - Absolute path to clone into (e.g. /home/jovyan/repo)
#   MAX_CLONE_TIMEOUT - Timeout in seconds for git operations
#
# Environment variables (optional):
#   BRANCH            - Branch or tag to check out (default: repository's default branch)

export HOME=/tmp

# Validate required environment variables
: "${REPO_URL:?REPO_URL environment variable is required}"
: "${CLONE_DIR:?CLONE_DIR environment variable is required}"
: "${MAX_CLONE_TIMEOUT:?MAX_CLONE_TIMEOUT environment variable is required}"

git config --global http.sslVerify true
git config --global user.email jupyterhub@local
git config --global user.name JupyterHub

# Inject token into HTTPS URLs via git URL rewriting.
# This approach works for all token types (classic PAT, fine-grained PAT, OAuth)
# because the token is embedded directly in the URL rather than going through
# the credential challenge/response flow.
# The rewrite targets only the actual host in REPO_URL, so it works for any provider.
if [ -n "${GIT_ACCESS_TOKEN:-}" ]; then
  _repo_host=$(echo "$REPO_URL" | sed 's|https://||' | cut -d/ -f1)
  git config --global \
    url."https://x-access-token:${GIT_ACCESS_TOKEN}@${_repo_host}/".insteadOf \
    "https://${_repo_host}/"
  unset _repo_host
fi

# Remove leftover clone directory from a previous session (e.g. preStop hook
# was skipped due to force-delete or node failure).
if [ -d "$CLONE_DIR" ]; then
  echo "Removing leftover directory $CLONE_DIR"
  rm -rf "$CLONE_DIR"
fi

if [ -n "${BRANCH:-}" ]; then
  echo "Cloning $REPO_URL (branch: $BRANCH) into $CLONE_DIR"
  if ! timeout "$MAX_CLONE_TIMEOUT" git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$CLONE_DIR"; then
    echo "Clone failed - check URL, branch name, and network access"
    exit 1
  fi
else
  echo "Cloning $REPO_URL into $CLONE_DIR"
  if ! timeout "$MAX_CLONE_TIMEOUT" git clone --depth 1 "$REPO_URL" "$CLONE_DIR"; then
    echo "Clone failed - check URL and network access"
    exit 1
  fi
fi

echo "Done"
