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

from setuptools import find_packages, setup

LABEXTENSION_SOURCE = Path("auplc_jupyterlab_runtime_status/labextension")
LABEXTENSION_TARGET = "share/jupyter/labextensions/@auplc/jupyterlab-runtime-status"


def get_labextension_data_files():
    if not LABEXTENSION_SOURCE.exists():
        return []

    files_by_directory = {}
    for path in LABEXTENSION_SOURCE.rglob("*"):
        if path.is_file():
            target_directory = Path(
                LABEXTENSION_TARGET,
                path.parent.relative_to(LABEXTENSION_SOURCE),
            )
            files_by_directory.setdefault(str(target_directory), []).append(str(path))

    return sorted(files_by_directory.items())


setup(
    packages=find_packages(),
    include_package_data=True,
    data_files=get_labextension_data_files()
    + [
        (
            "etc/jupyter/jupyter_server_config.d",
            ["jupyter-config/jupyter_server_config.d/auplc_jupyterlab_runtime_status.json"],
        ),
    ],
)
