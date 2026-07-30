# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-resource-contracts.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_resource_contracts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_resource_contracts"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verifier = load_verifier()


DEFAULT_PATHS = {
    "cpu": "/home/jovyan",
    "gpu": "/home/jovyan",
    "code-cpu": "/home/jovyan",
    "code-gpu": "/home/jovyan",
    "Course-CV": "/opt/workspace/CV",
    "Course-DL": "/opt/workspace/DL",
    "Course-LLM": "/opt/workspace/LLM",
    "Course-PhySim": "/opt/workspace/PhySim",
    "Course-Finetuning": "/ryzers/notebooks",
    "Course-LocalInference": "/ryzers/notebooks",
}


class FakeDocker:
    def __init__(
        self, working_dirs: dict[str, str], directories: set[tuple[str, str]], files: set[tuple[str, str]]
    ) -> None:
        self.working_dirs = working_dirs
        self.directories = directories
        self.files = files
        self.queries: list[tuple[str, str, str | None]] = []

    def image_working_dir(self, image: str) -> str:
        self.queries.append(("working-dir", image, None))
        return self.working_dirs[image]

    def directory_exists(self, image: str, path: str) -> bool:
        self.queries.append(("directory", image, path))
        return (image, path) in self.directories

    def file_exists(self, image: str, path: str) -> bool:
        self.queries.append(("file", image, path))
        return (image, path) in self.files


def write_values(tmp_path: Path, overrides: dict[str, Any] | None = None) -> Path:
    images = {key: f"example.test/{key}:latest" for key in verifier.OFFICIAL_RESOURCE_KEYS}
    images["Custom-URL"] = "example.test/custom:latest"
    metadata = {
        key: {
            "defaultPath": DEFAULT_PATHS[key],
            **({"launchMode": "code-server"} if key in {"code-cpu", "code-gpu"} else {}),
        }
        for key in verifier.OFFICIAL_RESOURCE_KEYS
    }
    metadata["Custom-URL"] = {"defaultPath": "/custom"}
    values = {"custom": {"resources": {"images": images, "metadata": metadata}}}
    for dotted_path, value in (overrides or {}).items():
        target = values
        parts = dotted_path.split(".")
        for part in parts[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[parts[-1]]
        else:
            target[parts[-1]] = value
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump(values), encoding="utf-8")
    return path


class _Delete:
    pass


_DELETE = _Delete()


def make_fake_docker() -> FakeDocker:
    working_dirs = {f"example.test/{key}:latest": DEFAULT_PATHS[key] for key in verifier.OFFICIAL_RESOURCE_KEYS}
    directories = {(f"example.test/{key}:latest", DEFAULT_PATHS[key]) for key in verifier.OFFICIAL_RESOURCE_KEYS}
    files = {
        ("example.test/code-cpu:latest", verifier.CODE_SERVER_START_SCRIPT),
        ("example.test/code-gpu:latest", verifier.CODE_SERVER_START_SCRIPT),
    }
    return FakeDocker(working_dirs=working_dirs, directories=directories, files=files)


def test_official_resource_contracts_pass_and_ignore_custom_resources(tmp_path: Path) -> None:
    values_file = write_values(tmp_path)
    docker = make_fake_docker()

    results = verifier.verify(values_file, docker)

    assert all(result.passed for result in results)
    queried_images = {query[1] for query in docker.queries}
    assert queried_images == {f"example.test/{key}:latest" for key in verifier.OFFICIAL_RESOURCE_KEYS}
    assert "example.test/custom:latest" not in queried_images


def test_default_path_normalization_matches_hub_container_path_semantics(tmp_path: Path) -> None:
    values_file = write_values(
        tmp_path,
        {"custom.resources.metadata.Course-CV.defaultPath": "//opt/./workspace//CV/"},
    )
    docker = make_fake_docker()

    results = verifier.verify(values_file, docker)

    assert all(result.passed for result in results)
    assert ("directory", "example.test/Course-CV:latest", "/opt/workspace/CV") in docker.queries


def test_working_dir_mismatch_fails_with_actionable_output(tmp_path: Path) -> None:
    values_file = write_values(tmp_path)
    docker = make_fake_docker()
    docker.working_dirs["example.test/Course-CV:latest"] = "/wrong"

    results = verifier.verify(values_file, docker)
    output = "\n".join(verifier.format_result(result) for result in results)

    assert any(not result.passed and result.check_name == "image-working-dir" for result in results)
    assert "FAIL resource=Course-CV image=example.test/Course-CV:latest check=image-working-dir" in output
    assert "expected=/opt/workspace/CV actual=/wrong" in output


def test_missing_official_default_path_fails(tmp_path: Path) -> None:
    values_file = write_values(
        tmp_path,
        {"custom.resources.metadata.Course-CV.defaultPath": _DELETE},
    )
    docker = make_fake_docker()

    results = verifier.verify(values_file, docker)

    assert any(
        not result.passed
        and result.resource_key == "Course-CV"
        and result.check_name == "defaultPath-present"
        and result.actual == "missing"
        for result in results
    )


def test_default_path_directory_must_exist_in_image(tmp_path: Path) -> None:
    values_file = write_values(tmp_path)
    docker = make_fake_docker()
    docker.directories.remove(("example.test/Course-DL:latest", "/opt/workspace/DL"))

    results = verifier.verify(values_file, docker)

    output = "\n".join(verifier.format_result(result) for result in results)

    assert "FAIL resource=Course-DL image=example.test/Course-DL:latest check=defaultPath-directory" in output
    assert "expected=/opt/workspace/DL actual=missing" in output


def test_code_server_launch_mode_requires_start_script(tmp_path: Path) -> None:
    values_file = write_values(tmp_path)
    docker = make_fake_docker()
    docker.files.remove(("example.test/code-cpu:latest", verifier.CODE_SERVER_START_SCRIPT))

    results = verifier.verify(values_file, docker)
    output = "\n".join(verifier.format_result(result) for result in results)

    assert "FAIL resource=code-cpu image=example.test/code-cpu:latest check=code-server-launcher" in output
    assert f"expected={verifier.CODE_SERVER_START_SCRIPT} actual=missing" in output
