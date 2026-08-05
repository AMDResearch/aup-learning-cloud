#!/usr/bin/env bash
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

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAUNCHER=$(cd "$SCRIPT_DIR/.." && pwd)/start-code-server.sh
SYSTEM_PATH=$PATH
NGINX_CONF=/tmp/auplc-code-server-nginx.conf
tmp_root=$(mktemp -d)
fake_bin="$tmp_root/fake-bin"
current_case=
launcher_pid=
last_launcher_status=

cleanup() {
  trap - EXIT INT TERM
  if [ -n "$launcher_pid" ]; then
    kill -TERM "$launcher_pid" 2>/dev/null || true
    wait "$launcher_pid" 2>/dev/null || true
  fi
  rm -f "$NGINX_CONF"
  rm -rf "$tmp_root"
}
trap cleanup EXIT INT TERM

fail() {
  if [ -n "$current_case" ]; then
    for file in "$current_case"/*.out "$current_case"/commands.log; do
      [ -f "$file" ] || continue
      printf '%s\n' "--- $file ---" >&2
      sed -n '1,200p' "$file" >&2
    done
  fi
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_eq() {
  [ "$1" = "$2" ] || fail "$3: expected '$1', got '$2'"
}

assert_file_contains() {
  grep -Fq -- "$2" "$1" || fail "expected $1 to contain: $2"
}

assert_file_not_contains() {
  if grep -Fq -- "$2" "$1"; then
    fail "did not expect $1 to contain: $2"
  fi
}

assert_process_gone() {
  if kill -0 "$1" 2>/dev/null; then
    fail "$2 process $1 is still running"
  fi
}

wait_for_file() {
  local file=$1
  local owner_pid=$2
  local description=$3
  local attempt
  for ((attempt = 0; attempt < 500; attempt++)); do
    [ -e "$file" ] && return 0
    kill -0 "$owner_pid" 2>/dev/null || fail "$description did not occur before launcher exited"
    sleep 0.01
  done
  fail "timed out waiting for $description"
}

new_case() {
  current_case="$tmp_root/$1"
  mkdir -p "$current_case"/{baked,destination,events,home,npm,pixi,workspace}
  : >"$current_case/commands.log"
  case_public_port=18888
  case_code_server_port=18889
  case_service_prefix=/user/test/
  case_trusted_domains=
  case_code_exit_status=
  case_nginx_exit_status=
}

start_launcher() {
  local instance=$1
  mkfifo \
    "$current_case/events/$instance.code.fifo" \
    "$current_case/events/$instance.code-exit.fifo" \
    "$current_case/events/$instance.nginx.fifo" \
    "$current_case/events/$instance.nginx-exit.fifo"

  PATH="$fake_bin:$SYSTEM_PATH" \
    HOME="$current_case/home" \
    NPM_CONFIG_PREFIX="$current_case/npm" \
    PIXI_HOME="$current_case/pixi" \
    PORT="$case_public_port" \
    AUPLC_CODE_SERVER_PORT="$case_code_server_port" \
    JUPYTERHUB_SERVICE_PREFIX="$case_service_prefix" \
    AUPLC_CODE_WORKDIR="$current_case/workspace" \
    AUPLC_CODE_TRUSTED_DOMAINS="$case_trusted_domains" \
    AUPLC_CODE_BAKED_EXTENSIONS_DIR="$current_case/baked" \
    AUPLC_CODE_EXTENSIONS_DIR="$current_case/destination" \
    FAKE_COMMAND_LOG="$current_case/commands.log" \
    FAKE_EVENT_DIR="$current_case/events" \
    FAKE_INSTANCE="$instance" \
    FAKE_CODE_EXIT_STATUS="$case_code_exit_status" \
    FAKE_NGINX_EXIT_STATUS="$case_nginx_exit_status" \
    bash "$LAUNCHER" >"$current_case/$instance.out" 2>&1 &
  launcher_pid=$!
}

wait_launcher() {
  local pid=$1
  set +e
  wait "$pid"
  last_launcher_status=$?
  set -e
  launcher_pid=
}

stop_launcher() {
  local instance=$1
  local pid=$2
  local code_pid
  local nginx_pid
  code_pid=$(<"$current_case/events/$instance.code-ready")
  nginx_pid=$(<"$current_case/events/$instance.nginx-ready")
  kill -TERM "$pid"
  wait_for_file "$current_case/events/$instance.code-term" "$pid" "code-server TERM handling"
  wait_for_file "$current_case/events/$instance.nginx-term" "$pid" "nginx TERM handling"
  wait_launcher "$pid"
  assert_eq 143 "$last_launcher_status" "TERM exit status"
  assert_process_gone "$code_pid" code-server
  assert_process_gone "$nginx_pid" nginx
}

mkdir -p "$fake_bin"
cp "$SCRIPT_DIR/fixtures/code-server" "$SCRIPT_DIR/fixtures/nginx" "$SCRIPT_DIR/fixtures/npm" "$fake_bin/"
chmod +x "$fake_bin"/*
