#!/usr/bin/env python3
# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
"""
Generate JSON Schema from values.schema.yaml

This script converts the YAML-format JSON Schema (values.schema.yaml) to
the JSON format (values.schema.json) that Helm uses for validation.

The values.schema.yaml is the source of truth, maintained manually with
descriptions. This script strips descriptions for the JSON output used
by Helm (to reduce chart size), while preserving the full schema structure.

Based on the approach used by Zero to JupyterHub (Z2JH):
https://github.com/jupyterhub/zero-to-jupyterhub-k8s

Usage:
    python generate_values_schema.py
    python generate_values_schema.py --keep-descriptions
"""

import argparse
import json
import sys
from pathlib import Path


def remove_descriptions(obj, in_properties=False):
    """
    Recursively remove 'description' keys from a schema object.

    Only removes 'description' when it's a JSON Schema documentation field,
    not when it's a property name inside 'properties'.
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            # Skip 'description' key only when not inside 'properties'
            # (i.e., when it's a schema documentation field)
            if k == "description" and not in_properties:
                continue
            # When we enter 'properties', mark that we're inside it
            if k == "properties":
                result[k] = {pk: remove_descriptions(pv, in_properties=False) for pk, pv in v.items()}
            else:
                result[k] = remove_descriptions(v, in_properties=False)
        return result
    elif isinstance(obj, list):
        return [remove_descriptions(item, in_properties=False) for item in obj]
    else:
        return obj


def main():
    parser = argparse.ArgumentParser(description="Generate values.schema.json from values.schema.yaml")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent.parent / "runtime" / "chart" / "values.schema.yaml",
        help="Path to values.schema.yaml (default: runtime/chart/values.schema.yaml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: values.schema.json next to input file)",
    )
    parser.add_argument(
        "--keep-descriptions",
        action="store_true",
        help="Keep description fields in output (larger file size)",
    )

    args = parser.parse_args()

    # Check input file exists
    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    # Import yaml
    try:
        import yaml
    except ImportError:
        print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    # Read and parse YAML schema
    with open(args.input) as f:
        schema = yaml.safe_load(f)

    # Remove descriptions unless --keep-descriptions is set
    if not args.keep_descriptions:
        schema = remove_descriptions(schema)

    # Determine output path
    output_path = args.output
    if output_path is None:
        output_path = args.input.with_suffix(".json")

    # Write JSON schema (compact format to reduce size)
    with open(output_path, "w") as f:
        if args.keep_descriptions:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        else:
            # Compact JSON for Helm chart (no extra whitespace)
            json.dump(schema, f, separators=(",", ":"), ensure_ascii=False)

    # Stats
    input_size = args.input.stat().st_size
    output_size = output_path.stat().st_size

    print(f"Generated: {output_path}")
    print(f"  Input:  {input_size:,} bytes ({args.input.name})")
    print(f"  Output: {output_size:,} bytes ({output_path.name})")
    if not args.keep_descriptions:
        print("  (descriptions stripped for smaller chart size)")


if __name__ == "__main__":
    main()
