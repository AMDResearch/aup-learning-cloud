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

new_case runtime-extension-model
mkdir -p "$current_case/baked/image.extension-1.0.0"
printf 'image extension\n' >"$current_case/baked/image.extension-1.0.0/package.json"
printf '[{"identifier":{"id":"image.extension"},"version":"1.0.0","location":{"scheme":"file","path":"%s"}}]\n' \
  "$current_case/baked/image.extension-1.0.0" >"$current_case/baked/extensions.json"
printf 'persistent sentinel\n' >"$current_case/destination/sentinel"
cp -a "$current_case/destination" "$current_case/expected-destination"

start_launcher one
pid=$launcher_pid
wait_for_file "$current_case/events/one.code-ready" "$pid" "code-server startup"
wait_for_file "$current_case/events/one.nginx-ready" "$pid" "nginx startup"
diff -r "$current_case/expected-destination" "$current_case/destination" >/dev/null || \
  fail "launcher mutated the persistent extension tree"
[ ! -e "$current_case/events/installer-invoked" ] || fail "launcher invoked a runtime extension installer"
assert_file_contains "$current_case/commands.log" "--extensions-dir $current_case/destination"
assert_eq 2 "$(grep -c 'extensions_dir' "$LAUNCHER")" "launcher extension-directory references"
for forbidden in --install-extension extensions.json flock seed merge; do
  assert_file_not_contains "$LAUNCHER" "$forbidden"
done
stop_launcher one "$pid"
printf 'runtime_extension_model=ok\n'
