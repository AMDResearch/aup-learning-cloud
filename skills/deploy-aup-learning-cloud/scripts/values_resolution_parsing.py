# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Fixed-shape parsing and overlay resolution for deploy values files."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ValuesFileParseResult:
    accelerators: dict[str, str | None]
    metadata: dict[str, list[str]]
    parse_errors: list[str]


@dataclass(frozen=True, slots=True)
class EffectiveValuesResult:
    accelerators: dict[str, str]
    metadata: dict[str, list[str]]
    missing_files: list[str]
    parse_errors: list[str]


def yaml_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def yaml_optional_scalar(value: str) -> str:
    scalar_value = yaml_scalar(value)
    return "" if scalar_value in {"", "null", "~"} else scalar_value


def yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def parse_inline_list(value: str) -> list[str]:
    items = value.strip()[1:-1].strip()
    if not items:
        return []
    return [yaml_scalar(item) for item in items.split(",") if yaml_scalar(item)]


def is_relevant_flow_path(path: tuple[str, ...]) -> bool:
    return path == ("custom",) or path[:2] in {("custom", "accelerators"), ("custom", "resources")}


def unsupported_yaml_syntax(value: str) -> bool:
    return value.startswith(("&", "*", "!", "|", ">"))


def parse_values_file(text: str) -> ValuesFileParseResult:
    accelerators: dict[str, str | None] = {}
    metadata: dict[str, list[str]] = {}
    parse_errors: list[str] = []
    stack: list[tuple[int, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = yaml_indent(line)
        stripped = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        path = tuple(key for _, key in stack)

        if stripped.startswith("- "):
            if len(path) == 5 and path[:3] == ("custom", "resources", "metadata") and path[-1] == "acceleratorKeys":
                metadata.setdefault(path[3], []).append(yaml_scalar(stripped[2:]))
            continue

        product_label_match = re.fullmatch(
            r"(?:[\"']amd\.com/gpu\.product-name[\"']|amd\.com/gpu\.product-name):\s*(.*)", stripped
        )
        if product_label_match:
            if len(path) == 4 and path[:2] == ("custom", "accelerators") and path[-1] == "nodeSelector":
                value = product_label_match.group(1).strip()
                if unsupported_yaml_syntax(value):
                    parse_errors.append(
                        f"unsupported YAML syntax at custom.accelerators.{path[2]}.nodeSelector.amd.com/gpu.product-name"
                    )
                else:
                    accelerators[path[2]] = yaml_optional_scalar(value)
            continue

        mapping_match = re.fullmatch(r"(.+?):(?:\s*(.*))?", stripped)
        if not mapping_match:
            continue
        key = mapping_match.group(1).strip("\"'")
        value = (mapping_match.group(2) or "").strip()
        candidate_path = path + (key,)
        if value.startswith("{") and value != "{}" and is_relevant_flow_path(candidate_path):
            parse_errors.append(f"unsupported non-empty flow-style mapping at {'.'.join(candidate_path)}")
        if unsupported_yaml_syntax(value) and is_relevant_flow_path(candidate_path):
            parse_errors.append(f"unsupported YAML syntax at {'.'.join(candidate_path)}")
        if path == ("custom", "accelerators"):
            accelerators.setdefault(key, None)
        if len(path) == 4 and path[:3] == ("custom", "resources", "metadata") and key == "acceleratorKeys":
            resource_key = path[3]
            if unsupported_yaml_syntax(value):
                parse_errors.append(f"unsupported YAML syntax at {'.'.join(candidate_path)}")
            elif value.startswith("[") and value.endswith("]"):
                metadata[resource_key] = parse_inline_list(value)
            elif not value or value in {"null", "~"}:
                metadata[resource_key] = []
            else:
                parse_errors.append(f"acceleratorKeys must be a list at {'.'.join(candidate_path)}")
        stack.append((indent, key))
    return ValuesFileParseResult(accelerators, metadata, parse_errors)


def collect_effective_values(repo: Path, values: list[str]) -> EffectiveValuesResult:
    accelerators: dict[str, str] = {}
    metadata: dict[str, list[str]] = {}
    missing_files: list[str] = []
    parse_errors: list[str] = []
    for rel in values or ["runtime/values.yaml"]:
        path = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if not path.exists():
            missing_files.append(f"values file not found: {rel}")
            continue
        parsed = parse_values_file(path.read_text(encoding="utf-8"))
        for key, selector in parsed.accelerators.items():
            if selector is not None or key not in accelerators:
                accelerators[key] = selector
        metadata.update(parsed.metadata)
        parse_errors.extend(parsed.parse_errors)
    return EffectiveValuesResult(accelerators, metadata, missing_files, parse_errors)
