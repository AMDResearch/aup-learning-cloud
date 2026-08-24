#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Generate AUP Learning Cloud deploy artifacts from a small cluster-spec.

Given a JSON cluster-spec (see ``--print-schema``), discover the managed hosts'
GPU policy. Both topologies immediately write mutually consistent canonical
deployment artifacts:

  1. ``inventory.yml``               -- Ansible inventory (server + token +
                                        k3s_version; agents listed for the
                                        SSH topology, empty for PXE).
  2. ``pb-pxe-controller.vars.yml``  -- PXE topology only: extra vars passed to
                                        pb-pxe-controller.yml with
                                        ``-e @<absolute-path>``.
  3. ``values-basic-example.yaml``   -- Helm overlay: storage, proxy, and
                                        authentication.
  4. ``gpu-access-resolution.json``  -- Machine-readable resolved host policy.

Design choices (deliberate):

  * stdlib only (json, argparse, secrets, base64, pathlib). No PyYAML, so this
    runs on a bare operator machine. YAML is emitted from templates, not a
    serialiser -- the output is small, fixed-shape, and carries the copyright header.
  * The k3s token is generated locally with ``secrets`` (CSPRNG). Canonical
    output writes it only into ``inventory.yml``. It is never printed to
    stdout/stderr. Pass ``--token-file`` to reuse an existing token instead of
    minting one.
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
    render_pxe_vars,
    render_values,
    validate_spec,
    validate_yaml_scalar,
)
from gpu_artifact_generation import DiscoveryFailure, canonical_paths, discover_gpu_policy, manifest_content


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
    args = ap.parse_args(argv)

    if args.print_schema:
        print(json.dumps(SCHEMA, indent=2))
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
    inventory, values, manifest = canonical_paths(out)
    artifacts = [(inventory, render_inventory(spec, token, discovery.resolution), 0o600, True)]
    pxe_gpu_access_enabled = None
    if topo == "pxe-diskless":
        pxe_gpu_access_enabled = spec["pxe"]["diskless_agents_have_amd_gpus"]
        artifacts.append(
            (out / "pb-pxe-controller.vars.yml", render_pxe_vars(spec, pxe_gpu_access_enabled), 0o600, True)
        )
    artifacts += [
        (values, render_values(spec), 0o644, False),
        (manifest, manifest_content(discovery, pxe_gpu_access_enabled), 0o644, False),
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
