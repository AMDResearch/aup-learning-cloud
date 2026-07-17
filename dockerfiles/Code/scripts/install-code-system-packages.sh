#!/usr/bin/env bash
set -euo pipefail

apt_packages_file="${1:?apt package list path is required}"
code_server_version="${CODE_SERVER_VERSION:?CODE_SERVER_VERSION is required}"
code_server_deb="/tmp/code-server.deb"
packages=()

while IFS= read -r package_name || [ -n "${package_name}" ]; do
  package_name="${package_name%%#*}"
  package_name="${package_name#"${package_name%%[![:space:]]*}"}"
  package_name="${package_name%"${package_name##*[![:space:]]}"}"

  if [ -n "${package_name}" ]; then
    packages+=("${package_name}")
  fi
done <"${apt_packages_file}"

apt-get update
apt-get install -y --no-install-recommends "${packages[@]}"
curl -fsSL \
  -o "${code_server_deb}" \
  "https://github.com/coder/code-server/releases/download/v${code_server_version}/code-server_${code_server_version}_amd64.deb"
apt-get install -y --no-install-recommends "${code_server_deb}"
rm -f "${code_server_deb}"
apt-get clean
rm -rf /var/lib/apt/lists/*
