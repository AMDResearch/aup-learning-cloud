#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Generate AUP Learning Cloud deploy artifacts from a small cluster-spec.

Given a JSON cluster-spec (see ``--print-schema``), discover the managed hosts'
GPU policy. SSH and PXE without GPU-enabled diskless agents immediately write
mutually consistent canonical deployment artifacts:

  1. ``inventory.yml``               -- Ansible inventory (server + token +
                                        k3s_version; agents listed for the
                                        SSH topology, empty for PXE).
  2. ``pb-pxe-controller.vars.yml``  -- PXE topology only: extra vars passed to
                                        pb-pxe-controller.yml with
                                        ``-e @<absolute-path>``.
  3. ``values-basic-example.yaml``   -- Helm overlay: resolved render GID,
                                        storage, proxy, and authentication.
  4. ``gpu-access-resolution.json``  -- Machine-readable resolved host policy.

GPU-enabled PXE instead writes private ``.pxe-bootstrap.inventory.yml``,
``.pxe-bootstrap.vars.yml``, and ``.pxe-finalizer-context.json`` files while
canonical artifacts remain absent. The controller playbook publishes the
canonical artifacts only after it resolves the rootfs GID and succeeds.

Design choices (deliberate):

  * stdlib only (json, argparse, secrets, base64, pathlib). No PyYAML, so this
    runs on a bare operator machine. YAML is emitted from templates, not a
    serialiser -- the output is small, fixed-shape, and carries the copyright header.
  * The k3s token is generated locally with ``secrets`` (CSPRNG). Immediate
    canonical output writes it only into ``inventory.yml``. Pending GPU-enabled
    PXE stores it only in private ``.pxe-finalizer-context.json`` until the
    controller succeeds and finalization writes ``inventory.yml``. It is never
    printed to stdout/stderr. Pass ``--token-file`` to reuse an existing token
    instead of minting one.
  * ``pxe_k3s_version`` is forced equal to ``k3s_version`` so agents can never
    be newer than the server (k3s refuses that).
  * Existing files are not overwritten unless ``--force`` is given.

Usage:
    gen_configs.py --print-schema
    gen_configs.py --spec spec.json --out-dir ./generated
    cat spec.json | gen_configs.py --spec - --out-dir ./generated --force

Exit codes: 0 on success; 1 on a spec/validation error; 2 on a usage error.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
from pathlib import Path

from artifact_store import preflight_destinations, publish_artifacts
from config_common import DuplicateJsonKeyError, strict_json_loads
from config_generation import (
    SCHEMA,
    die,
    render_inventory,
    render_values,
    validate_spec,
    validate_yaml_scalar,
)
from gpu_artifact_generation import DiscoveryFailure, canonical_paths, discover_gpu_policy, manifest_content
from pxe_finalization import FinalizationError, finalize, publish_disabled_rootfs, stage_pending


def gen_token() -> str:
    # Mirror `openssl rand -base64 64`: 64 random bytes, base64-encoded.
    return base64.b64encode(secrets.token_bytes(64)).decode("ascii")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", help="path to the cluster-spec JSON, or - for stdin")
    ap.add_argument("--out-dir", default="generated", help="directory to write artifacts into (default: ./generated)")
    ap.add_argument("--token-file", help="read the k3s token from this file instead of generating one")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--print-schema", action="store_true", help="print an example cluster-spec and exit")
    ap.add_argument("--finalize-pxe", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--context", help=argparse.SUPPRESS)
    ap.add_argument("--handoff", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.print_schema:
        print(json.dumps(SCHEMA, indent=2))
        return 0
    if args.finalize_pxe:
        if args.spec or args.token_file or args.context is None or args.handoff is None:
            die("--finalize-pxe requires --out-dir, --context, and --handoff", 2)
        try:
            finalize(Path(args.out_dir), Path(args.context), Path(args.handoff))
        except FinalizationError as error:
            die(str(error))
        return 0
    if not args.spec:
        die("--spec is required (or use --print-schema)", 2)

    raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text(encoding="utf-8")
    try:
        spec = strict_json_loads(raw)
    except (DuplicateJsonKeyError, json.JSONDecodeError) as exc:
        die(f"spec is not valid JSON: {exc}")

    topo = validate_spec(spec)
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        validate_yaml_scalar(token, "--token-file")
    else:
        token = gen_token()

    out = Path(args.out_dir)
    try:
        discovery = discover_gpu_policy(spec, out)
    except DiscoveryFailure as error:
        die(str(error))
    if topo == "pxe-diskless":
        try:
            if spec["pxe"]["diskless_agents_have_amd_gpus"]:
                stage_pending(spec, token, discovery.resolution, out, args.force)
                print("PXE GPU rootfs is pending finalization after pb-pxe-controller.yml resolves its render GID.")
            else:
                publish_disabled_rootfs(spec, token, discovery.resolution, out, args.force)
        except FinalizationError as error:
            die(str(error))
    else:
        inventory, values, manifest = canonical_paths(out)
        artifacts = [(inventory, render_inventory(spec, token, discovery.resolution), 0o600, True)]
        artifacts += [
            (values, render_values(spec, discovery.resolution), 0o644, False),
            (manifest, manifest_content(discovery), 0o644, False),
        ]
        preflight_destinations([path for path, _, _, _ in artifacts], args.force)
        publish_artifacts(artifacts, args.force)

    print(
        "\nNext: review the files, then copy them into your aup-learning-cloud "
        "checkout. Never commit inventory.yml -- it holds the k3s token."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
