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

from pathlib import Path
from typing import Protocol, TypedDict

import yaml


class SpawnerValues(TypedDict):
    http_timeout: int


class HubConfigValues(TypedDict):
    Spawner: SpawnerValues


class HubValues(TypedDict):
    config: HubConfigValues
    consecutiveFailureLimit: int


class SingleuserValues(TypedDict):
    startTimeout: int


class SpawnDefaults(TypedDict):
    hub: HubValues
    singleuser: SingleuserValues


class YamlLoader(Protocol):
    def safe_load(self, stream: str, /) -> SpawnDefaults: ...


def load_yaml(loader: YamlLoader, stream: str) -> SpawnDefaults:
    return loader.safe_load(stream)


def test_spawn_defaults() -> None:
    values_path = Path(__file__).resolve().parents[3] / "runtime" / "chart" / "values.yaml"
    values = load_yaml(
        yaml,
        values_path.read_text(encoding="utf-8"),
    )

    assert values["hub"]["config"]["Spawner"]["http_timeout"] == 60
    assert values["hub"]["consecutiveFailureLimit"] == 0
    assert values["singleuser"]["startTimeout"] == 300
