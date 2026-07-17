#!/usr/bin/env bash
set -euo pipefail

pixi_version="${PIXI_VERSION:-v0.68.1}"
pixi_download_url="${PIXI_DOWNLOAD_URL:-}"
pixi_conda_forge_mirror="${PIXI_CONDA_FORGE_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge}"

if [ -z "${pixi_download_url}" ]; then
  case "$(uname -m)" in
    x86_64) pixi_arch="x86_64" ;;
    aarch64) pixi_arch="aarch64" ;;
    *)
      printf 'Unsupported Pixi architecture: %s\n' "$(uname -m)" >&2
      exit 1
      ;;
  esac

  pixi_download_url="https://github.com/prefix-dev/pixi/releases/download/${pixi_version}/pixi-${pixi_arch}-unknown-linux-musl"
fi

curl -fsSL --compressed -o /usr/local/bin/pixi "${pixi_download_url}"
chmod +x /usr/local/bin/pixi

mkdir -p /etc/pixi
if [ -n "${pixi_conda_forge_mirror}" ]; then
  cat >/etc/pixi/config.toml <<EOF
tls-root-certs = "native"
default-channels = ["conda-forge"]

[mirrors]
"https://conda.anaconda.org/conda-forge" = [
  "${pixi_conda_forge_mirror}",
]
EOF
else
  cat >/etc/pixi/config.toml <<'EOF'
tls-root-certs = "native"
default-channels = ["conda-forge"]
EOF
fi

pixi --version
