#!/usr/bin/env python3
# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Verify official AUPLC resource image contracts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALUES_FILE = REPO_ROOT / "runtime" / "values.yaml"
OFFICIAL_RESOURCE_KEYS = (
    "cpu",
    "gpu",
    "code-cpu",
    "code-gpu",
    "Course-CV",
    "Course-DL",
    "Course-LLM",
    "Course-PhySim",
    "Course-Finetuning",
    "Course-LocalInference",
)
CODE_SERVER_START_SCRIPT = "/usr/local/bin/start-code-server.sh"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ResourceContract:
    key: str
    image: str
    metadata: dict[str, Any]

    @property
    def default_path(self) -> Any:
        return self.metadata.get("defaultPath")

    @property
    def launch_mode(self) -> str:
        return str(self.metadata.get("launchMode") or "")


@dataclass(frozen=True)
class CheckResult:
    resource_key: str
    image: str
    check_name: str
    passed: bool
    expected: str
    actual: str


class DockerClient:
    def __init__(self, runner: Callable[[Sequence[str]], CommandResult] | None = None) -> None:
        self._runner = runner or run_command

    def image_working_dir(self, image: str) -> str:
        result = self._runner(["docker", "image", "inspect", "--format", "{{json .Config.WorkingDir}}", image])
        if result.returncode != 0:
            return command_failure(result)
        output = result.stdout.strip()
        if not output:
            return ""
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return output
        return "" if parsed is None else str(parsed)

    def directory_exists(self, image: str, path: str) -> bool:
        result = self._runner(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/bin/sh",
                "-e",
                f"AUPLC_CONTRACT_PATH={path}",
                image,
                "-c",
                'test -d "$AUPLC_CONTRACT_PATH"',
            ]
        )
        return result.returncode == 0

    def file_exists(self, image: str, path: str) -> bool:
        result = self._runner(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/bin/sh",
                "-e",
                f"AUPLC_CONTRACT_PATH={path}",
                image,
                "-c",
                'test -f "$AUPLC_CONTRACT_PATH"',
            ]
        )
        return result.returncode == 0


def run_command(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return CommandResult(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def command_failure(result: CommandResult) -> str:
    detail = (result.stderr or result.stdout).strip()
    if not detail:
        detail = f"command exited {result.returncode}"
    return f"ERROR: {detail}"


def load_values(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as values_file:
        loaded = yaml.safe_load(values_file) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} did not contain a YAML mapping")
    return loaded


def get_nested_mapping(data: dict[str, Any], path: Sequence[str]) -> dict[str, Any]:
    current: Any = data
    for part in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(part, {})
    return current if isinstance(current, dict) else {}


def build_contracts(values: dict[str, Any]) -> list[ResourceContract]:
    images = get_nested_mapping(values, ("custom", "resources", "images"))
    metadata = get_nested_mapping(values, ("custom", "resources", "metadata"))
    contracts: list[ResourceContract] = []
    for key in OFFICIAL_RESOURCE_KEYS:
        resource_metadata = metadata.get(key, {})
        if not isinstance(resource_metadata, dict):
            resource_metadata = {}
        image = images.get(key, "")
        contracts.append(ResourceContract(key=key, image=str(image or "<missing image>"), metadata=resource_metadata))
    return contracts


def normalize_default_path(value: Any) -> str:
    if value is None:
        raise ValueError("defaultPath is missing")
    if not isinstance(value, str):
        raise ValueError("defaultPath must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError("defaultPath cannot be empty")
    if "\x00" in stripped:
        raise ValueError("defaultPath cannot contain NUL bytes")
    if not stripped.startswith("/"):
        raise ValueError("defaultPath must be an absolute container path")
    segments: list[str] = []
    for segment in stripped.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            raise ValueError("defaultPath cannot contain '..' segments")
        segments.append(segment)
    return "/" if not segments else "/" + "/".join(segments)


def pass_result(contract: ResourceContract, check_name: str, expected: str, actual: str) -> CheckResult:
    return CheckResult(contract.key, contract.image, check_name, True, expected, actual)


def fail_result(contract: ResourceContract, check_name: str, expected: str, actual: str) -> CheckResult:
    return CheckResult(contract.key, contract.image, check_name, False, expected, actual)


def check_default_path_syntax(contract: ResourceContract, docker: DockerClient) -> CheckResult:
    del docker
    try:
        normalized = normalize_default_path(contract.default_path)
    except ValueError as exc:
        return fail_result(contract, "defaultPath-syntax", "valid absolute container path", str(exc))
    return pass_result(contract, "defaultPath-syntax", "valid absolute container path", normalized)


def check_default_path_present(contract: ResourceContract, docker: DockerClient) -> CheckResult:
    del docker
    if contract.default_path is None:
        return fail_result(contract, "defaultPath-present", "metadata.defaultPath", "missing")
    return pass_result(contract, "defaultPath-present", "metadata.defaultPath", str(contract.default_path))


def check_image_working_dir(contract: ResourceContract, docker: DockerClient) -> CheckResult:
    try:
        expected = normalize_default_path(contract.default_path)
    except ValueError as exc:
        return fail_result(contract, "image-working-dir", "valid metadata.defaultPath", str(exc))
    actual = docker.image_working_dir(contract.image)
    if actual != expected:
        return fail_result(contract, "image-working-dir", expected, actual)
    return pass_result(contract, "image-working-dir", expected, actual)


def check_default_path_directory(contract: ResourceContract, docker: DockerClient) -> CheckResult:
    try:
        expected = normalize_default_path(contract.default_path)
    except ValueError as exc:
        return fail_result(contract, "defaultPath-directory", "valid metadata.defaultPath", str(exc))
    exists = docker.directory_exists(contract.image, expected)
    actual = "exists" if exists else "missing"
    if not exists:
        return fail_result(contract, "defaultPath-directory", expected, actual)
    return pass_result(contract, "defaultPath-directory", expected, actual)


def check_code_server_launcher(contract: ResourceContract, docker: DockerClient) -> CheckResult:
    if contract.launch_mode != "code-server":
        actual = contract.launch_mode or "default"
        return pass_result(contract, "code-server-launcher", "not required unless launchMode=code-server", actual)
    exists = docker.file_exists(contract.image, CODE_SERVER_START_SCRIPT)
    actual = "exists" if exists else "missing"
    if not exists:
        return fail_result(contract, "code-server-launcher", CODE_SERVER_START_SCRIPT, actual)
    return pass_result(contract, "code-server-launcher", CODE_SERVER_START_SCRIPT, actual)


Check = Callable[[ResourceContract, DockerClient], CheckResult]
CHECKS: tuple[Check, ...] = (
    check_default_path_syntax,
    check_default_path_present,
    check_image_working_dir,
    check_default_path_directory,
    check_code_server_launcher,
)


def run_checks(contracts: Sequence[ResourceContract], docker: DockerClient) -> list[CheckResult]:
    results: list[CheckResult] = []
    for contract in contracts:
        for check in CHECKS:
            results.append(check(contract, docker))
    return results


def format_result(result: CheckResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    return (
        f"{status} resource={result.resource_key} image={result.image} "
        f"check={result.check_name} expected={result.expected} actual={result.actual}"
    )


def print_results(results: Sequence[CheckResult]) -> None:
    for result in results:
        print(format_result(result))
    failures = [result for result in results if not result.passed]
    print(f"SUMMARY official_resources={len(OFFICIAL_RESOURCE_KEYS)} checks={len(results)} failures={len(failures)}")


def verify(values_file: Path, docker: DockerClient) -> list[CheckResult]:
    values = load_values(values_file)
    contracts = build_contracts(values)
    return run_checks(contracts, docker)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify official resource image contracts.")
    parser.add_argument(
        "--values-file",
        type=Path,
        default=DEFAULT_VALUES_FILE,
        help="Values file to read. Defaults to canonical runtime/values.yaml.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    results = verify(args.values_file, DockerClient())
    print_results(results)
    return 1 if any(not result.passed for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
