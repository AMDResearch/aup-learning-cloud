#!/usr/bin/env bash
set -euo pipefail

pnpm_version="${PNPM_VERSION:?PNPM_VERSION is required}"
npm_registry="${NPM_REGISTRY:-}"
global_packages="${CODE_GLOBAL_NPM_PACKAGES:-typescript tsx vite eslint prettier}"
global_package_args=()

if [ -n "${npm_registry}" ]; then
  npm config set registry "${npm_registry}"
  export COREPACK_NPM_REGISTRY="${npm_registry}"
fi

corepack enable
corepack prepare "pnpm@${pnpm_version}" --activate
npm install -g --omit=dev --force "pnpm@${pnpm_version}"

if [ -n "${global_packages}" ]; then
  read -r -a global_package_args <<<"${global_packages}"
  npm install -g --omit=dev "${global_package_args[@]}"
fi

node --version
npm --version
npx --version
pnpm --version
