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
# Clones a repository onto the user's home PVC. Existing clone directories are
# reused or replaced only when repo-external AUPLC metadata proves they are
# managed by this script.
#
# Environment variables (required):
#   REPO_URL          - HTTPS URL of the git repository to clone
#   CLONE_DIR         - Absolute path to clone into (e.g. /home/jovyan/repo)
#   MAX_CLONE_TIMEOUT - Timeout in seconds for git operations
#
# Environment variables (optional):
#   BRANCH            - Branch or tag to check out (default: repository's default branch)
#   PERSIST_CLONED_REPO - true to reuse a compatible managed clone (default: true)
#   AUPLC_GIT_METADATA_DIR - Directory for repo-external clone metadata

export HOME=/tmp

# Validate required environment variables
: "${REPO_URL:?REPO_URL environment variable is required}"
: "${CLONE_DIR:?CLONE_DIR environment variable is required}"
: "${MAX_CLONE_TIMEOUT:?MAX_CLONE_TIMEOUT environment variable is required}"

git config --global http.sslVerify true
git config --global user.email jupyterhub@local
git config --global user.name JupyterHub

case "${PERSIST_CLONED_REPO:-true}" in
  true|True|TRUE|1|yes|Yes|YES)
    _persistence_mode="persistent"
    ;;
  false|False|FALSE|0|no|No|NO)
    _persistence_mode="ephemeral"
    ;;
  *)
    echo "Invalid PERSIST_CLONED_REPO value. Use true or false."
    exit 1
    ;;
esac

_metadata_dir=${AUPLC_GIT_METADATA_DIR:-"$(dirname "$CLONE_DIR")/.auplc/git-clones"}
_clone_base=$(basename "$CLONE_DIR" | tr -c 'A-Za-z0-9._-' '_' | sed 's/^_*//; s/_*$//')
if [ -z "$_clone_base" ]; then
  _clone_base="clone"
fi
_clone_hash=$(printf '%s' "$CLONE_DIR" | cksum | cut -d ' ' -f 1)
_metadata_file="$_metadata_dir/${_clone_base}-${_clone_hash}.metadata"
_metadata_version="1"
_branch_value=${BRANCH:-}

sanitize_repo_url() {
  _url=$1
  case "$_url" in
    https://*)
      _sanitize_scheme="https://"
      _sanitize_rest=${_url#https://}
      ;;
    http://*)
      _sanitize_scheme="http://"
      _sanitize_rest=${_url#http://}
      ;;
    *)
      printf '%s' "$_url"
      return 0
      ;;
  esac

  _sanitize_authority=${_sanitize_rest%%/*}
  case "$_sanitize_authority" in
    *@*)
      _sanitize_authority=${_sanitize_authority##*@}
      ;;
    *)
      ;;
  esac

  case "$_sanitize_rest" in
    */*)
      printf '%s%s/%s' "$_sanitize_scheme" "$_sanitize_authority" "${_sanitize_rest#*/}"
      ;;
    *)
      printf '%s%s' "$_sanitize_scheme" "$_sanitize_authority"
      ;;
  esac
}

metadata_value() {
  _key=$1
  _file=$2
  if [ ! -f "$_file" ]; then
    return 1
  fi
  sed -n "s/^${_key}=//p" "$_file" | sed -n '1p'
}

is_metadata_compatible() {
  _file=$1
  [ "$(metadata_value state "$_file")" = "complete" ] || return 1
  [ "$(metadata_value version "$_file")" = "$_metadata_version" ] || return 1
  [ "$(metadata_value clone_dir "$_file")" = "$CLONE_DIR" ] || return 1
  [ "$(metadata_value repo_url "$_file")" = "$_sanitized_repo_url" ] || return 1
  [ "$(metadata_value branch "$_file")" = "$_branch_value" ] || return 1
  return 0
}

write_metadata() {
  mkdir -p "$_metadata_dir"
  _tmp_metadata="$_metadata_file.tmp.$$"
  {
    printf 'version=%s\n' "$_metadata_version"
    printf 'state=complete\n'
    printf 'clone_dir=%s\n' "$CLONE_DIR"
    printf 'repo_url=%s\n' "$_sanitized_repo_url"
    printf 'branch=%s\n' "$_branch_value"
    printf 'persistence_mode=%s\n' "$_persistence_mode"
    date -u '+timestamp=%Y-%m-%dT%H:%M:%SZ'
  } > "$_tmp_metadata"
  mv "$_tmp_metadata" "$_metadata_file"
}

clone_repo() {
  rm -f "$_metadata_file" "$_metadata_file.tmp.$$"
  mkdir -p "$(dirname "$CLONE_DIR")"
  if [ -n "${BRANCH:-}" ]; then
    echo "Cloning $_sanitized_repo_url (branch: $BRANCH) into $CLONE_DIR"
    if ! timeout "$MAX_CLONE_TIMEOUT" git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$CLONE_DIR"; then
      rm -f "$_metadata_file.tmp.$$"
      echo "Clone failed - check URL, branch name, and network access"
      exit 1
    fi
  else
    echo "Cloning $_sanitized_repo_url into $CLONE_DIR"
    if ! timeout "$MAX_CLONE_TIMEOUT" git clone --depth 1 "$REPO_URL" "$CLONE_DIR"; then
      rm -f "$_metadata_file.tmp.$$"
      echo "Clone failed - check URL and network access"
      exit 1
    fi
  fi
  write_metadata
}

_sanitized_repo_url=$(sanitize_repo_url "$REPO_URL")

# Inject token into HTTPS URLs via git URL rewriting.
# This approach works for all token types (classic PAT, fine-grained PAT, OAuth)
# because the token is embedded directly in the URL rather than going through
# the credential challenge/response flow.
# The rewrite targets only the actual host in REPO_URL, so it works for any provider.
if [ -n "${GIT_ACCESS_TOKEN:-}" ]; then
  case "$_sanitized_repo_url" in
    https://*)
      _repo_host=$(printf '%s' "$_sanitized_repo_url" | sed 's|https://||' | cut -d/ -f1)
      git config --global \
        url."https://x-access-token:${GIT_ACCESS_TOKEN}@${_repo_host}/".insteadOf \
        "https://${_repo_host}/"
      ;;
    *)
      ;;
  esac
  unset _repo_host
fi

if [ -d "$CLONE_DIR" ]; then
  if ! is_metadata_compatible "$_metadata_file"; then
    echo "Refusing to modify existing directory $CLONE_DIR without compatible AUPLC clone metadata"
    exit 1
  fi

  _metadata_persistence_mode=$(metadata_value persistence_mode "$_metadata_file")
  case "$_persistence_mode:$_metadata_persistence_mode" in
    persistent:persistent)
      echo "Reusing existing managed clone $CLONE_DIR"
      exit 0
      ;;
    persistent:ephemeral)
      write_metadata
      echo "Reusing existing managed clone $CLONE_DIR"
      exit 0
      ;;
    ephemeral:ephemeral)
      echo "Replacing existing managed ephemeral clone $CLONE_DIR"
      rm -rf "$CLONE_DIR"
      ;;
    ephemeral:persistent)
      echo "Refusing to replace persistent managed clone $CLONE_DIR for an ephemeral request"
      exit 1
      ;;
    *)
      echo "Refusing to modify existing directory $CLONE_DIR with unknown metadata persistence mode"
      exit 1
      ;;
  esac
fi

clone_repo

echo "Done"
