# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
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
"""Regression coverage for the SSH client inbox-driver admission checks."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "deploy/ansible/roles/rocm/tasks"
TASKS = yaml.safe_load((ROLE / "preflight.yml").read_text(encoding="utf-8"))
ENV = Environment(undefined=StrictUndefined)
ENV.filters["from_json"] = json.loads


def admits(name, **facts):
    task = next(task for task in TASKS if task["name"] == name)
    return all(ENV.compile_expression(expr)(**facts) for expr in task["ansible.builtin.assert"]["that"])


class TestClientGpuAdmission(unittest.TestCase):
    def test_ubuntu_firmware_is_allowed_but_each_legacy_package_blocks(self):
        name = "Reject AMD DKMS driver and firmware packages"
        clean = {"linux-firmware": [], "linux-firmware-amd-graphics": []}
        self.assertTrue(admits(name, ansible_facts={"packages": clean}))
        for package in ("amdgpu-dkms", "amdgpu-dkms-firmware", "rock-dkms", "rock-dkms-firmware"):
            with self.subTest(package=package):
                self.assertFalse(admits(name, ansible_facts={"packages": {**clean, package: []}}))

    def test_module_origin_checks_oem_and_generic_without_a_version_cutoff(self):
        name = "Require the Ubuntu inbox amdgpu module"
        for kernel in ("6.14.0-1018-oem", "6.17.0-14-generic"):
            with self.subTest(kernel=kernel):
                self.assertTrue(
                    admits(
                        name,
                        _auplc_amdgpu_path={
                            "rc": 0,
                            "stdout": f"/lib/modules/{kernel}/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.zst",
                        },
                        _auplc_amdgpu_intree={"rc": 0, "stdout": "Y\n"},
                    )
                )
        for path, rc, intree in (
            ("/lib/modules/example/updates/dkms/amdgpu.ko", 0, "Y"),
            ("/lib/modules/example/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko", 0, ""),
            ("", 1, "Y"),
        ):
            with self.subTest(path=path, rc=rc, intree=intree):
                self.assertFalse(
                    admits(
                        name,
                        _auplc_amdgpu_path={"rc": rc, "stdout": path},
                        _auplc_amdgpu_intree={"rc": 0, "stdout": intree},
                    )
                )

    def test_loaded_dkms_and_missing_devices_block_even_when_disk_module_is_valid(self):
        name = "Require an active inbox driver and AMD compute devices"
        healthy = {"loaded": True, "taint": "", "kfd": True, "render_nodes": ["/dev/dri/renderD128"]}
        self.assertTrue(admits(name, _auplc_amdgpu_runtime={"stdout": json.dumps(healthy)}))
        for change in ({"loaded": False}, {"taint": "OE"}, {"kfd": False}, {"render_nodes": []}):
            with self.subTest(change=change):
                self.assertFalse(admits(name, _auplc_amdgpu_runtime={"stdout": json.dumps({**healthy, **change})}))

    @unittest.skipIf(os.name == "nt", "Requires Linux character devices and symlinks")
    def test_probe_counts_only_amd_amdgpu_character_render_devices(self):
        probe = next(task for task in TASKS if task["name"] == "Inspect the loaded GPU driver and compute devices")
        code = probe["ansible.builtin.command"]["argv"][-1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def write(relative, text):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")

            write("sys/module/amdgpu/taint", "")
            (root / "dev/dri").mkdir(parents=True)
            (root / "dev/kfd").symlink_to("/dev/null")
            for number, vendor, driver, character in (
                (128, "0x1002", "amdgpu", True),
                (129, "0x8086", "i915", True),
                (130, "0x1002", "vfio-pci", True),
                (131, "0x1002", "amdgpu", False),
            ):
                device = f"sys/class/drm/renderD{number}/device"
                write(f"{device}/vendor", vendor)
                (root / device / "driver").symlink_to(root / "drivers" / driver)
                node = root / f"dev/dri/renderD{number}"
                if character:
                    node.symlink_to("/dev/null")
                else:
                    node.touch()
            output = io.StringIO()
            with (
                patch("pathlib.Path", side_effect=lambda path: root / path.lstrip("/")),
                contextlib.redirect_stdout(output),
            ):
                exec(compile(code, "<GPU probe>", "exec"), {})
            result = json.loads(output.getvalue())
            self.assertTrue(result["loaded"])
            self.assertTrue(result["kfd"])
            self.assertEqual(result["render_nodes"], [str(root / "dev/dri/renderD128")])


if __name__ == "__main__":
    unittest.main()
