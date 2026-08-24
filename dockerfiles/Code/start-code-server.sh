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
extensions_dir="${AUPLC_CODE_EXTENSIONS_DIR:-/home/jovyan/.local/share/code-server/extensions}"
trusted_domains="${AUPLC_CODE_TRUSTED_DOMAINS:-}"
code_server_pid=
nginx_pid=
cleanup_status=
pid=

trap '
  cleanup_status=$?
  trap - EXIT INT TERM
  for pid in "${code_server_pid}" "${nginx_pid}"; do
    if [ -n "${pid}" ]; then
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  done
  for pid in "${code_server_pid}" "${nginx_pid}"; do
    if [ -n "${pid}" ]; then
      wait "${pid}" 2>/dev/null || true
    fi
  done
  exit "${cleanup_status}"
' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "${NPM_CONFIG_PREFIX}/bin"
mkdir -p "${PIXI_HOME}/bin"
npm config set prefix "${NPM_CONFIG_PREFIX}" >/dev/null

url_decode() {
  local value="${1//+/ }"
  printf '%b' "${value//%/\\x}"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

build_trusted_domain_args() {
  local domains_csv="$1"
  local -n output_args="$2"
  local -a domains=()
  local domain

  IFS=',' read -ra domains <<<"${domains_csv}"
  for domain in "${domains[@]}"; do
    domain="$(trim "${domain}")"
    if [ -n "${domain}" ]; then
      output_args+=(--link-protection-trusted-domains "${domain}")
    fi
  done
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

trusted_domain_args=()
build_trusted_domain_args "${trusted_domains}" trusted_domain_args

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

env -u PORT code-server \
  --auth none \
  --bind-addr "127.0.0.1:${code_server_port}" \
  --extensions-dir "${extensions_dir}" \
  "${trusted_domain_args[@]}" \
  --ignore-last-opened \
  "${workdir}" &
code_server_pid="$!"

nginx -c "${nginx_conf}" -g 'daemon off;' &
nginx_pid="$!"

exited_pid=
set +e
wait -n -p exited_pid "${nginx_pid}" "${code_server_pid}"
child_status=$?
set -e
if [ "${exited_pid}" = "${nginx_pid}" ]; then
  nginx_pid=
elif [ "${exited_pid}" = "${code_server_pid}" ]; then
  code_server_pid=
fi
exit "${child_status}"
