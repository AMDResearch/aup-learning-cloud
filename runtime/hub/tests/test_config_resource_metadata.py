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

import importlib.util
import sys
import types
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


config = load_module("core.config", CORE / "config.py")
ResourceMetadata = config.ResourceMetadata


def test_resource_metadata_default_path_omitted_or_null_stays_none():
    assert ResourceMetadata().defaultPath is None
    assert ResourceMetadata(defaultPath=None).defaultPath is None


@pytest.mark.parametrize(
    ("default_path", "expected_message"),
    [
        ("", "defaultPath cannot be empty"),
        ("   ", "defaultPath cannot be empty"),
        ("workspace/CV", "defaultPath must be an absolute container path"),
        ("/opt/../secret", "defaultPath cannot contain '..' segments"),
        ("/opt/\x00secret", "defaultPath cannot contain NUL bytes"),
    ],
)
def test_resource_metadata_default_path_rejects_invalid_syntax(default_path: str, expected_message: str):
    with pytest.raises(ValidationError, match=expected_message):
        ResourceMetadata(defaultPath=default_path)


@pytest.mark.parametrize(
    ("default_path", "expected_path"),
    [
        ("/", "/"),
        ("/opt/workspace/CV", "/opt/workspace/CV"),
        ("/home/jovyan/", "/home/jovyan"),
        ("//opt/./workspace//CV/", "/opt/workspace/CV"),
        ("  /home/jovyan/  ", "/home/jovyan"),
    ],
)
def test_resource_metadata_default_path_normalizes_valid_paths(default_path: str, expected_path: str):
    metadata = ResourceMetadata(defaultPath=default_path)

    assert metadata.defaultPath == expected_path
