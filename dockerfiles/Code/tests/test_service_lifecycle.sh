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
# shellcheck source-path=SCRIPTDIR
# shellcheck source=harness.sh
source "$SCRIPT_DIR/harness.sh"

test_launch_contract_and_port_isolation() {
  new_case launch-contract
  case_public_port=19080
  case_code_server_port=19081
  case_service_prefix=/user/alice%40example/
  case_trusted_domains='hub.example, docs.example'
  start_launcher one
  local pid=$launcher_pid
  wait_for_file "$current_case/events/one.code-ready" "$pid" "code-server startup"
  wait_for_file "$current_case/events/one.nginx-ready" "$pid" "nginx startup"
  assert_file_contains "$current_case/commands.log" "code-server --auth none"
  assert_file_contains "$current_case/commands.log" "--bind-addr 127.0.0.1:19081"
  assert_file_contains "$current_case/commands.log" "--extensions-dir $current_case/destination"
  assert_file_contains "$current_case/commands.log" "--link-protection-trusted-domains hub.example"
  assert_file_contains "$current_case/commands.log" "--link-protection-trusted-domains docs.example"
  assert_file_contains "$current_case/commands.log" "--ignore-last-opened $current_case/workspace"
  assert_eq '<unset>' "$(<"$current_case/events/one.code-port-env")" "code-server PORT environment"
  assert_file_contains "$current_case/events/one.nginx.conf" "listen 0.0.0.0:19080;"
  assert_file_contains "$current_case/events/one.nginx.conf" "location /user/alice@example/"
  assert_file_contains "$current_case/events/one.nginx.conf" "proxy_pass http://127.0.0.1:19081;"
  stop_launcher one "$pid"
}

test_term_returns_143_and_reaps_services() {
  new_case term-cleanup
  start_launcher one
  local pid=$launcher_pid
  wait_for_file "$current_case/events/one.code-ready" "$pid" "code-server startup"
  wait_for_file "$current_case/events/one.nginx-ready" "$pid" "nginx startup"
  stop_launcher one "$pid"
}

test_code_server_exit_cleans_nginx() {
  new_case code-first-exit
  case_code_exit_status=37
  start_launcher one
  local pid=$launcher_pid
  wait_for_file "$current_case/events/one.code-ready" "$pid" "code-server startup"
  wait_for_file "$current_case/events/one.nginx-ready" "$pid" "nginx startup"
  local nginx_pid
  nginx_pid=$(<"$current_case/events/one.nginx-ready")
  printf 'exit\n' >"$current_case/events/one.code-exit.fifo"
  wait_for_file "$current_case/events/one.nginx-term" "$pid" "nginx sibling cleanup"
  wait_launcher "$pid"
  assert_eq 37 "$last_launcher_status" "code-server first exit status"
  assert_process_gone "$nginx_pid" nginx
}

test_nginx_exit_cleans_code_server() {
  new_case nginx-first-exit
  case_nginx_exit_status=38
  start_launcher one
  local pid=$launcher_pid
  wait_for_file "$current_case/events/one.code-ready" "$pid" "code-server startup"
  wait_for_file "$current_case/events/one.nginx-ready" "$pid" "nginx startup"
  local code_pid
  code_pid=$(<"$current_case/events/one.code-ready")
  printf 'exit\n' >"$current_case/events/one.nginx-exit.fifo"
  wait_for_file "$current_case/events/one.code-term" "$pid" "code-server sibling cleanup"
  wait_launcher "$pid"
  assert_eq 38 "$last_launcher_status" "nginx first exit status"
  assert_process_gone "$code_pid" code-server
}

test_launch_contract_and_port_isolation
test_term_returns_143_and_reaps_services
test_code_server_exit_cleans_nginx
test_nginx_exit_cleans_code_server
printf 'service_lifecycle_tests=ok\n'
