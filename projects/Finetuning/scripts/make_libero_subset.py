#!/usr/bin/env python3
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Build a small, self-consistent subset of a LeRobot v3.0 dataset (e.g. the MolmoAct2 LIBERO
dataset) so the workshop payload is ~1 GB instead of ~33 GB. The subset is a drop-in replacement:
same repo id, same HF-cache layout (blobs/ + snapshots/<sha>/ + refs/main), so staging and the
notebook's offline prefetch keep working unchanged, and `lerobot-train` trains on exactly the
episodes present (no episode list is hard-coded in the notebook).

Two selection modes:

  stratified (default) - round-robin across every task so the subset keeps a LARGE task
      distribution (all/most tasks represented), not just the first few. Episodes are then
      non-contiguous in the source, so the data parquet files are re-packed and the global
      `index` / `episode_index` columns and per-episode metadata are re-numbered. `task_index`
      values are preserved and `tasks.parquet` is kept whole, so no task re-mapping is needed.

  prefix - keep a contiguous prefix of data files (fast, reuses the original cache blobs, no
      re-encode) but only covers the first tasks. Handy for a quick tiny build.

The kept episode set is always derived from the ACTUAL `episode_index` values inside the data
parquet files, because this dataset's meta `data/file_index` column does NOT line up with the
parquet file numbering.

Usage:
  make_libero_subset.py --repo-cache <hf_hub>/datasets--allenai--MolmoAct2-LIBERO-Dataset \
                        --out <out_hf_hub> [--target-gb 1.0] [--mode stratified|prefix] \
                        [--episodes-per-task N]

<out_hf_hub> ends up containing datasets--<repo>/ ready to tar into the workshop bundle
(unpack_bundle.sh extracts it straight into ASSETS_DIR/hf_hub).
"""
import argparse
import hashlib
import io
import json
import os
import shutil
from collections import defaultdict

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _snapshot_dir(repo_cache):
    sha = open(os.path.join(repo_cache, "refs", "main")).read().strip()
    snap = os.path.join(repo_cache, "snapshots", sha)
    if not os.path.isdir(snap):
        raise SystemExit(f"snapshot dir not found for refs/main={sha}: {snap}")
    return sha, snap


def _link_only(out_snap, rel, blob_abs):
    link = os.path.join(out_snap, rel)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.relpath(blob_abs, start=os.path.dirname(link)), link)


def _reuse_blob(src_snap, out_repo, out_snap, rel):
    """Reuse the ORIGINAL cache blob for an unchanged file (copy blob + relative symlink)."""
    blob = os.path.realpath(os.path.join(src_snap, rel))
    dst = os.path.join(out_repo, "blobs", os.path.basename(blob))
    if not os.path.exists(dst):
        shutil.copy2(blob, dst)
    _link_only(out_snap, rel, dst)


def _write_blob(out_repo, out_snap, rel, data_bytes):
    """Write NEW content as a fresh blob + snapshot symlink."""
    h = _sha256_bytes(data_bytes)
    dst = os.path.join(out_repo, "blobs", h)
    if not os.path.exists(dst):
        with open(dst, "wb") as f:
            f.write(data_bytes)
    _link_only(out_snap, rel, dst)


def _table_bytes(tbl):
    buf = io.BytesIO()
    pq.write_table(tbl, buf)
    return buf.getvalue()


def _build_ep_to_file(snap, data_files):
    """Map episode_index -> data filename by reading the ACTUAL episode_index column of each file
    (meta data/file_index is unreliable for this dataset). Assumes an episode lives in one file."""
    ep2file = {}
    for fn in data_files:
        col = pq.read_table(
            os.path.realpath(os.path.join(snap, "data", "chunk-000", fn)), columns=["episode_index"]
        ).column("episode_index").to_pylist()
        for e in set(col):
            ep2file[int(e)] = fn
    return ep2file


def _select_stratified(ep, target_frames, episodes_per_task):
    """Round-robin across tasks (by task string set) until ~target_frames, capped per task."""
    n = len(ep["episode_index"])
    groups = defaultdict(list)
    for i in range(n):
        groups[tuple(ep["tasks"][i])].append(i)
    task_keys = sorted(groups, key=lambda k: min(groups[k]))
    for k in task_keys:
        groups[k].sort()
    pos = {k: 0 for k in task_keys}
    taken = {k: 0 for k in task_keys}
    selected, frames = [], 0
    progressed = True
    while frames < target_frames and progressed:
        progressed = False
        for k in task_keys:
            if pos[k] < len(groups[k]) and (episodes_per_task <= 0 or taken[k] < episodes_per_task):
                e = groups[k][pos[k]]
                pos[k] += 1
                taken[k] += 1
                selected.append(e)
                frames += int(ep["length"][e])
                progressed = True
                if frames >= target_frames:
                    break
    return sorted(selected), len(task_keys)


def _select_prefix(snap, data_files, sizes, target_bytes):
    cum, n_files = 0, 0
    for i, s in enumerate(sizes):
        cum += s
        n_files = i + 1
        if cum >= target_bytes:
            break
    kept_eps = set()
    for i in range(n_files):
        col = pq.read_table(
            os.path.realpath(os.path.join(snap, "data", "chunk-000", data_files[i])),
            columns=["episode_index"],
        ).column("episode_index").to_pylist()
        kept_eps.update(int(x) for x in col)
    return sorted(kept_eps), n_files


def _repack(snap, out_repo, out_snap, ep_tbl, ep, selected, ep2file, data_files_size_mb):
    """Re-pack the selected episodes' rows into new data parquet files with renumbered global
    `index` (0..N-1) and `episode_index` (0..K-1); rebuild meta/episodes accordingly."""
    thresh = int(data_files_size_mb * 1e6)
    buf, buf_bytes, fidx, g = [], 0, 0, 0
    new_ep_file = {}  # new_ep -> data file index
    written = []  # (fidx, table)
    cached_fn, cached_tbl = None, None

    def flush():
        nonlocal buf, buf_bytes, fidx
        if not buf:
            return
        tbl = pa.concat_tables(buf)
        _write_blob(out_repo, out_snap, f"data/chunk-000/file-{fidx:03d}.parquet", _table_bytes(tbl))
        fidx += 1
        buf, buf_bytes = [], 0

    lengths = []
    for new_ep, e in enumerate(selected):
        fn = ep2file[e]
        if fn != cached_fn:
            cached_tbl = pq.read_table(os.path.realpath(os.path.join(snap, "data", "chunk-000", fn)))
            cached_fn = fn
        rows = cached_tbl.filter(pc.equal(cached_tbl.column("episode_index"), e))
        m = rows.num_rows
        idx_arr = pa.array(list(range(g, g + m)), type=pa.int64())
        ep_arr = pa.array([new_ep] * m, type=pa.int64())
        rows = rows.set_column(rows.schema.get_field_index("index"), "index", idx_arr)
        rows = rows.set_column(rows.schema.get_field_index("episode_index"), "episode_index", ep_arr)
        new_ep_file[new_ep] = fidx
        g += m
        lengths.append(m)
        buf.append(rows)
        buf_bytes += rows.nbytes
        if buf_bytes >= thresh:
            flush()
    flush()
    total_frames = g

    # rebuild meta/episodes: take selected rows (in order), renumber the bookkeeping columns
    sub = ep_tbl.take(pa.array(selected, type=pa.int64()))
    K = len(selected)
    froms, tos, acc = [], [], 0
    for L in lengths:
        froms.append(acc)
        tos.append(acc + L)
        acc += L

    def setcol(t, name, arr):
        return t.set_column(t.schema.get_field_index(name), name, pa.array(arr, type=pa.int64()))

    sub = setcol(sub, "episode_index", list(range(K)))
    sub = setcol(sub, "dataset_from_index", froms)
    sub = setcol(sub, "dataset_to_index", tos)
    sub = setcol(sub, "data/chunk_index", [0] * K)
    sub = setcol(sub, "data/file_index", [new_ep_file[i] for i in range(K)])
    if "meta/episodes/chunk_index" in sub.column_names:
        sub = setcol(sub, "meta/episodes/chunk_index", [0] * K)
        sub = setcol(sub, "meta/episodes/file_index", [0] * K)
    # cross-check meta length column matches actual rows
    meta_len = sub.column("length").to_pylist()
    assert meta_len == lengths, "meta length column disagrees with packed rows"
    _write_blob(out_repo, out_snap, "meta/episodes/chunk-000/file-000.parquet", _table_bytes(sub))
    return K, total_frames, fidx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--target-gb", type=float, default=1.0)
    ap.add_argument("--mode", choices=["stratified", "prefix"], default="stratified")
    ap.add_argument("--episodes-per-task", type=int, default=0,
                    help="stratified: cap episodes taken per task (0 = no cap)")
    args = ap.parse_args()

    repo_cache = os.path.abspath(args.repo_cache)
    repo_name = os.path.basename(repo_cache.rstrip("/"))
    sha, snap = _snapshot_dir(repo_cache)

    info = json.load(open(os.path.join(snap, "meta", "info.json")))
    ep_tbl = pq.read_table(os.path.join(snap, "meta", "episodes", "chunk-000", "file-000.parquet"))
    ep = ep_tbl.to_pydict()
    n_ep_total = len(ep["episode_index"])
    assert ep["episode_index"] == list(range(n_ep_total)), "meta episodes not 0..N contiguous"

    data_dir = os.path.join(snap, "data", "chunk-000")
    data_files = sorted(f for f in os.listdir(data_dir) if f.endswith(".parquet"))
    sizes = [os.path.getsize(os.path.realpath(os.path.join(data_dir, f))) for f in data_files]
    total_bytes = sum(sizes)
    bytes_per_frame = total_bytes / info["total_frames"]

    out_repo = os.path.join(os.path.abspath(args.out), repo_name)
    out_snap = os.path.join(out_repo, "snapshots", sha)
    os.makedirs(os.path.join(out_repo, "blobs"), exist_ok=True)
    os.makedirs(out_snap, exist_ok=True)
    os.makedirs(os.path.join(out_repo, "refs"), exist_ok=True)
    open(os.path.join(out_repo, "refs", "main"), "w").write(sha)

    # unchanged files reused from the original cache
    reuse = ["meta/stats.json", "meta/tasks.parquet"]
    for opt in (".gitattributes", "README.md"):
        if os.path.lexists(os.path.join(snap, opt)):
            reuse.append(opt)

    print(f"source: {repo_name} sha={sha[:12]} episodes={n_ep_total} tasks={info['total_tasks']} "
          f"frames={info['total_frames']} ({total_bytes/1e9:.1f} GB, {bytes_per_frame/1e3:.0f} KB/frame)")

    if args.mode == "prefix":
        selected, n_files = _select_prefix(snap, data_files, sizes, args.target_gb * 1e9)
        assert selected == list(range(len(selected))), "prefix episodes not contiguous 0..N"
        K = len(selected)
        total_frames = int(ep["dataset_to_index"][K - 1])
        # reuse the original data-file blobs 0..n_files-1 as-is
        for i in range(n_files):
            reuse.append(f"data/chunk-000/{data_files[i]}")
        for rel in reuse:
            _reuse_blob(snap, out_repo, out_snap, rel)
        _write_blob(out_repo, out_snap, "meta/episodes/chunk-000/file-000.parquet",
                    _table_bytes(ep_tbl.slice(0, K)))
        n_data = n_files
        tasks = sorted({t for row in ep["tasks"][:K] for t in row})
    else:
        target_frames = int(args.target_gb * 1e9 / bytes_per_frame)
        selected, n_tasks = _select_stratified(ep, target_frames, args.episodes_per_task)
        for rel in reuse:
            _reuse_blob(snap, out_repo, out_snap, rel)
        ep2file = _build_ep_to_file(snap, data_files)
        K, total_frames, n_data = _repack(
            snap, out_repo, out_snap, ep_tbl, ep, selected, ep2file, info["data_files_size_in_mb"]
        )
        tasks = sorted({t for e in selected for t in ep["tasks"][e]})

    info["total_episodes"] = K
    info["total_frames"] = total_frames
    info["splits"] = {"train": f"0:{K}"}
    _write_blob(out_repo, out_snap, "meta/info.json", (json.dumps(info, indent=4) + "\n").encode())

    kept_bytes = sum(
        os.path.getsize(os.path.realpath(p))
        for p in [os.path.join(out_snap, "data", "chunk-000", f)
                  for f in os.listdir(os.path.join(out_snap, "data", "chunk-000"))]
    )
    print(f"mode={args.mode}  ->  {K} episodes, {total_frames} frames, {n_data} data files, "
          f"{len(tasks)}/{info['total_tasks']} tasks, {kept_bytes/1e9:.2f} GB")
    print(f"wrote subset -> {out_repo}")


if __name__ == "__main__":
    main()
