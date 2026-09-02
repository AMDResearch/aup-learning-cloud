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
from typing import final

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[1] / "core" / "jupyterhub_config.py"
TemplateValue = bool | str
ConfigValue = bool | int | str | None


@final
class ConfigSection:
    def __init__(self) -> None:
        self.template_vars: dict[str, TemplateValue] = {}
        self.tornado_settings: dict[str, int | dict[str, bool | str]] = {}
        self.volumes: list[dict[str, ConfigValue]] = []
        self.volume_mounts: list[dict[str, ConfigValue]] = []

    def get(self, _key: str, default: str) -> str:
        return default

    def update(self, _values: dict[str, ConfigValue]) -> None:
        return None


@final
class StubConfig:
    def __init__(self) -> None:
        self.JupyterHub = ConfigSection()
        self.ConfigurableHTTPProxy = ConfigSection()
        self.KubeSpawner = ConfigSection()
        self.Spawner = ConfigSection()
        self.CryptKeeper = ConfigSection()

    def __getitem__(self, _key: str) -> ConfigSection:
        return ConfigSection()


def test_startup_preserves_setup_and_deployment_template_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    config = StubConfig()
    setup_template_vars = {
        "auth_auto_login": False,
        "auth_dummy": False,
        "auth_native": True,
        "auth_github": True,
        "password_management_enabled": True,
        "hide_logout": False,
        "cluster_name": "test-cluster",
        "platform_name": "Test Platform",
    }
    deployment_template_vars = {"deployment_marker": "kept"}

    core = types.ModuleType("core")
    z2jh = types.ModuleType("core.z2jh")

    def get_config(key: str, default: ConfigValue | dict[str, ConfigValue] = None):
        if key == "hub.templateVars":
            return deployment_template_vars
        if key == "hub.db.type":
            return "sqlite-memory"
        return default

    def get_config_dict(_key: str) -> dict[str, ConfigValue]:
        return {}

    def get_config_list(_key: str) -> list[ConfigValue]:
        return []

    def get_name(name: str) -> str:
        return name

    def get_name_env(_name: str, _suffix: str) -> str:
        return "8081"

    def get_secret_value(_key: str, default: ConfigValue = None) -> ConfigValue:
        return default

    def set_config_if_not_none(_section: ConfigSection, _trait: str, _key: str) -> None:
        return None

    z2jh.__dict__.update(
        get_config=get_config,
        get_config_dict=get_config_dict,
        get_config_list=get_config_list,
        get_name=get_name,
        get_name_env=get_name_env,
        get_secret_value=get_secret_value,
        set_config_if_not_none=set_config_if_not_none,
    )
    core.__dict__["z2jh"] = z2jh

    config_module = types.ModuleType("core.config")

    class StubHubConfig:
        @staticmethod
        def init(config_path: str) -> None:
            assert config_path.endswith("hub-config.yaml")

        @staticmethod
        def get():
            return types.SimpleNamespace(hub_network=types.SimpleNamespace(allowedOrigins=[]))

    config_module.__dict__["HubConfig"] = StubHubConfig
    setup_module = types.ModuleType("core.setup")

    def setup_hub(hub_config: StubConfig) -> None:
        hub_config.JupyterHub.template_vars = dict(setup_template_vars)

    setup_module.__dict__["setup_hub"] = setup_hub

    kubernetes_asyncio = types.ModuleType("kubernetes_asyncio")
    kubernetes_client = types.ModuleType("kubernetes_asyncio.client")
    kubernetes_asyncio.__dict__["client"] = kubernetes_client
    tornado = types.ModuleType("tornado")
    tornado_httpclient = types.ModuleType("tornado.httpclient")

    class StubAsyncHTTPClient:
        @staticmethod
        def configure(_backend: str) -> None:
            return None

    tornado_httpclient.__dict__["AsyncHTTPClient"] = StubAsyncHTTPClient
    tornado.__dict__["httpclient"] = tornado_httpclient

    for module in (
        core,
        z2jh,
        config_module,
        setup_module,
        kubernetes_asyncio,
        kubernetes_client,
        tornado,
        tornado_httpclient,
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    spec = importlib.util.spec_from_file_location("startup_order_jupyterhub_config", CONFIG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__dict__["get_config"] = lambda: config
    spec.loader.exec_module(module)

    assert dict(config.JupyterHub.template_vars) == {
        **setup_template_vars,
        # powered_by follows platform_name so the footer shows the cluster name.
        "powered_by": "Test Platform",
        **deployment_template_vars,
    }
    headers = config.JupyterHub.tornado_settings["headers"]
    assert isinstance(headers, dict)
    assert headers["X-Powered-By"] == "AUP Learning Cloud"
