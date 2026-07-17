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

from .handlers import RuntimeStatusMetadataHandler, build_runtime_metadata_payload, setup_handlers

__version__ = "0.0.0"


def _jupyter_labextension_paths():
    return [
        {
            "src": "labextension",
            "dest": "@auplc/jupyterlab-runtime-status",
        }
    ]


def _jupyter_server_extension_points():
    return [{"module": "auplc_jupyterlab_runtime_status"}]


def _load_jupyter_server_extension(server_app):
    setup_handlers(server_app.web_app)


__all__ = [
    "RuntimeStatusMetadataHandler",
    "build_runtime_metadata_payload",
    "setup_handlers",
]
