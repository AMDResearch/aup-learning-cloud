#!/usr/bin/env bash
set -euo pipefail

export USER="${USER:-jovyan}"
export SHELL="${SHELL:-/bin/bash}"
export PIXI_HOME="${PIXI_HOME:-${HOME:-/home/jovyan}/.pixi}"
export PATH="${HOME:-/home/jovyan}/.local/bin:${PIXI_HOME}/bin:${PATH}"
export NPM_CONFIG_PREFIX="${NPM_CONFIG_PREFIX:-${HOME:-/home/jovyan}/.local}"

public_port="${PORT:-8888}"
code_server_port="${AUPLC_CODE_SERVER_PORT:-8889}"
service_prefix="${JUPYTERHUB_SERVICE_PREFIX:-/}"
# Without a Hub-provided launch override, open code-server in the image WORKDIR.
workdir="${AUPLC_CODE_WORKDIR:-$(pwd)}"
extensions_list="${AUPLC_CODE_EXTENSIONS_LIST:-/opt/auplc/extensions/extensions.txt}"
local_extensions_dir="${AUPLC_CODE_LOCAL_EXTENSIONS_DIR:-/opt/auplc/extensions/local}"
extensions_dir="${AUPLC_CODE_EXTENSIONS_DIR:-/home/jovyan/.local/share/code-server/extensions}"

mkdir -p "${NPM_CONFIG_PREFIX}/bin"
mkdir -p "${PIXI_HOME}/bin"
npm config set prefix "${NPM_CONFIG_PREFIX}" >/dev/null

url_decode() {
  local value="${1//+/ }"
  printf '%b' "${value//%/\\x}"
}

seed_builtin_extensions() {
  mkdir -p "${extensions_dir}"

  if [ -f "${extensions_list}" ]; then
    while IFS= read -r extension_id || [ -n "${extension_id}" ]; do
      case "${extension_id}" in
        ''|'#'*) continue ;;
        *) ;;
      esac

      if ! code-server --extensions-dir "${extensions_dir}" --install-extension "${extension_id}" --force; then
        printf 'Warning: failed to install code-server extension %s\n' "${extension_id}" >&2
      fi
    done <"${extensions_list}"
  fi

  if [ -d "${local_extensions_dir}" ]; then
    while IFS= read -r -d '' vsix_path; do
      if ! code-server --extensions-dir "${extensions_dir}" --install-extension "${vsix_path}"; then
        printf 'Warning: failed to install code-server extension package %s\n' "${vsix_path}" >&2
      fi
    done < <(find "${local_extensions_dir}" -type f -name '*.vsix' -print0)
  fi
}

case "${service_prefix}" in
  /*) ;;
  *) service_prefix="/${service_prefix}" ;;
esac

case "${service_prefix}" in
  */) ;;
  *) service_prefix="${service_prefix}/" ;;
esac

nginx_prefix="$(url_decode "${service_prefix}")"
regex_prefix="$(printf '%s' "${nginx_prefix}" | sed "s/[.[\\*^\$()+?{}|]/\\\\&/g")"
nginx_conf="/tmp/auplc-code-server-nginx.conf"
redirect_block=""

seed_builtin_extensions

if [ "${service_prefix}" != "/" ]; then
  redirect_block="
    location = ${nginx_prefix%/} {
      return 302 ${service_prefix};
    }
"
fi

cat >"${nginx_conf}" <<EOF
pid /tmp/auplc-code-server-nginx.pid;
error_log /dev/stderr info;
events {}
http {
  access_log /dev/stdout;

  client_body_temp_path /tmp/client_body;
  proxy_temp_path /tmp/proxy;
  fastcgi_temp_path /tmp/fastcgi;
  uwsgi_temp_path /tmp/uwsgi;
  scgi_temp_path /tmp/scgi;

  map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
  }

  server {
    listen 0.0.0.0:${public_port};
    absolute_redirect off;
    client_max_body_size 0;
${redirect_block}

    location ${nginx_prefix} {
      rewrite ^${regex_prefix}(.*)\$ /\$1 break;
      proxy_pass http://127.0.0.1:${code_server_port};
      proxy_http_version 1.1;
      proxy_set_header Host \$http_host;
      proxy_set_header X-Forwarded-Host \$http_host;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection \$connection_upgrade;
      proxy_set_header X-Real-IP \$remote_addr;
      proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto \$scheme;
      proxy_read_timeout 86400;
      proxy_redirect off;
    }
  }
}
EOF

code-server \
  --auth none \
  --bind-addr "127.0.0.1:${code_server_port}" \
  --extensions-dir "${extensions_dir}" \
  --ignore-last-opened \
  "${workdir}" &
code_server_pid="$!"

nginx -c "${nginx_conf}" -g 'daemon off;' &
nginx_pid="$!"

cleanup() {
  kill "${nginx_pid}" "${code_server_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "${nginx_pid}" "${code_server_pid}"
