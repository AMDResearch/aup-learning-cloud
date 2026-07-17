#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
GIT_CLONE_SCRIPT="$REPO_ROOT/runtime/hub/core/scripts/git-clone.sh"
ARTIFACT_DIR=${AUPLC_TEST_ARTIFACT_DIR:-"$REPO_ROOT/.sisyphus/evidence/task-9-credential-artifacts"}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_file_contains() {
  local file=$1
  local expected=$2
  if ! grep -Fq "$expected" "$file"; then
    printf '--- %s ---\n' "$file" >&2
    sed -n '1,160p' "$file" >&2
    fail "expected to find: $expected"
  fi
}

assert_file_not_contains() {
  local file=$1
  local unexpected=$2
  if grep -Fq "$unexpected" "$file"; then
    printf '--- %s ---\n' "$file" >&2
    sed -n '1,160p' "$file" >&2
    fail "did not expect to find: $unexpected"
  fi
}

metadata_file_for() {
  local metadata_dir=$1
  local file
  shopt -s nullglob
  local files=("$metadata_dir"/*.metadata)
  shopt -u nullglob
  if [ "${#files[@]}" -ne 1 ]; then
    fail "expected exactly one metadata file in $metadata_dir, found ${#files[@]}"
  fi
  file=${files[0]}
  printf '%s' "$file"
}

run_clone() {
  local repo_url=$1
  local clone_dir=$2
  local metadata_dir=$3
  local persist=$4
  local output_file=$5

  REPO_URL=$repo_url \
    CLONE_DIR=$clone_dir \
    AUPLC_GIT_METADATA_DIR=$metadata_dir \
    PERSIST_CLONED_REPO=$persist \
    MAX_CLONE_TIMEOUT=30 \
    sh "$GIT_CLONE_SCRIPT" >"$output_file" 2>&1
}

make_source_repo() {
  local repo_dir=$1
  git init -q "$repo_dir"
  git -C "$repo_dir" config user.email test@example.local
  git -C "$repo_dir" config user.name Test
  printf 'initial\n' >"$repo_dir/README.md"
  git -C "$repo_dir" add README.md
  git -C "$repo_dir" commit -q -m initial
}

tmp_root=$(mktemp -d)
trap 'rm -rf "$tmp_root"' EXIT
rm -rf "$ARTIFACT_DIR"
mkdir -p "$ARTIFACT_DIR"

source_repo="$tmp_root/source-repo"
make_source_repo "$source_repo"

for persist in true false; do
  clone_dir="$tmp_root/unmanaged-$persist/course"
  metadata_dir="$tmp_root/unmanaged-$persist/metadata"
  output_file="$tmp_root/unmanaged-$persist.out"
  mkdir -p "$clone_dir"
  printf 'user data\n' >"$clone_dir/user-marker.txt"
  if run_clone "$source_repo" "$clone_dir" "$metadata_dir" "$persist" "$output_file"; then
    fail "unmanaged directory was modified in $persist mode"
  fi
  assert_file_contains "$output_file" "Refusing to modify existing directory"
  [ -f "$clone_dir/user-marker.txt" ] || fail "unmanaged marker was removed in $persist mode"
done
printf 'unmanaged_same_name_directories=protected\n'

persistent_clone="$tmp_root/persistent/course"
persistent_metadata="$tmp_root/persistent/metadata"
run_clone "$source_repo" "$persistent_clone" "$persistent_metadata" true "$tmp_root/persistent-first.out"
printf 'user marker\n' >"$persistent_clone/user-marker.txt"
printf 'upstream change\n' >"$source_repo/UPSTREAM.md"
git -C "$source_repo" add UPSTREAM.md
git -C "$source_repo" commit -q -m upstream-change
run_clone "$source_repo" "$persistent_clone" "$persistent_metadata" true "$tmp_root/persistent-second.out"
assert_file_contains "$tmp_root/persistent-second.out" "Reusing existing managed clone"
[ -f "$persistent_clone/user-marker.txt" ] || fail "persistent marker was removed"
[ ! -f "$persistent_clone/UPSTREAM.md" ] || fail "persistent reuse pulled upstream changes"
printf 'persistent_reuse=preserved_user_files_without_pull_or_reset\n'

other_source_repo="$tmp_root/other-source-repo"
make_source_repo "$other_source_repo"
repo_mismatch_clone="$tmp_root/repo-mismatch/course"
repo_mismatch_metadata="$tmp_root/repo-mismatch/metadata"
run_clone "$source_repo" "$repo_mismatch_clone" "$repo_mismatch_metadata" true "$tmp_root/repo-mismatch-first.out"
printf 'user marker\n' >"$repo_mismatch_clone/user-marker.txt"
if run_clone "$other_source_repo" "$repo_mismatch_clone" "$repo_mismatch_metadata" true "$tmp_root/repo-mismatch-second.out"; then
  fail "repo URL mismatch modified existing managed clone"
fi
assert_file_contains "$tmp_root/repo-mismatch-second.out" "Refusing to modify existing directory $repo_mismatch_clone without compatible AUPLC clone metadata"
[ -f "$repo_mismatch_clone/user-marker.txt" ] || fail "repo URL mismatch marker was removed"
printf 'repo_url_mismatch=preserved_user_files_and_refused\n'

upgrade_clone="$tmp_root/upgrade/course"
upgrade_metadata="$tmp_root/upgrade/metadata"
run_clone "$source_repo" "$upgrade_clone" "$upgrade_metadata" false "$tmp_root/upgrade-ephemeral.out"
printf 'user marker\n' >"$upgrade_clone/user-marker.txt"
run_clone "$source_repo" "$upgrade_clone" "$upgrade_metadata" true "$tmp_root/upgrade-persistent.out"
upgrade_metadata_file=$(metadata_file_for "$upgrade_metadata")
assert_file_contains "$upgrade_metadata_file" "persistence_mode=persistent"
if run_clone "$source_repo" "$upgrade_clone" "$upgrade_metadata" false "$tmp_root/upgrade-refuse-ephemeral.out"; then
  fail "ephemeral request replaced upgraded persistent clone"
fi
assert_file_contains "$tmp_root/upgrade-refuse-ephemeral.out" "Refusing to replace persistent managed clone"
[ -f "$upgrade_clone/user-marker.txt" ] || fail "upgraded persistent marker was removed"
printf 'persistent_reuse_upgrades_old_ephemeral_metadata=ok\n'

fake_bin="$tmp_root/fake-bin"
mkdir -p "$fake_bin"
cat >"$fake_bin/git" <<'FAKE_GIT'
#!/bin/sh
if [ "$1" = "config" ]; then
  exit 0
fi
if [ "$1" = "clone" ]; then
  destination=
  for arg in "$@"; do
    destination=$arg
  done
  mkdir -p "$destination/.git"
  printf 'fake clone\n' >"$destination/README.md"
  exit 0
fi
exit 0
FAKE_GIT
chmod +x "$fake_bin/git"

sentinel_token="TASK9_FAKE_TOKEN_SHOULD_NOT_LEAK"
token_clone="$tmp_root/token/private-repo"
token_metadata="$tmp_root/token/metadata"
token_output="$ARTIFACT_DIR/token-output.txt"
PATH="$fake_bin:$PATH" \
  REPO_URL="https://x-access-token:${sentinel_token}@github.com/example/private-repo" \
  CLONE_DIR="$token_clone" \
  AUPLC_GIT_METADATA_DIR="$token_metadata" \
  PERSIST_CLONED_REPO=true \
  MAX_CLONE_TIMEOUT=30 \
  sh "$GIT_CLONE_SCRIPT" >"$token_output" 2>&1
cp "$(metadata_file_for "$token_metadata")" "$ARTIFACT_DIR/token.metadata"
assert_file_contains "$ARTIFACT_DIR/token.metadata" "repo_url=https://github.com/example/private-repo"
assert_file_not_contains "$token_output" "$sentinel_token"
assert_file_not_contains "$ARTIFACT_DIR/token.metadata" "$sentinel_token"
if grep -R "$sentinel_token" "$ARTIFACT_DIR"; then
  fail "sentinel token leaked into captured clone output or metadata"
fi
printf 'credential_sanitization=ok\n'
