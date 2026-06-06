"""jupyterlab_rocm - JupyterLab extension for AMD ROCm GPU monitoring and profiling."""

try:
    from ._version import __version__
except ImportError:
    # Fallback when the package is not built (e.g. running from source before
    # the hatch version hook has generated _version.py).
    __version__ = "0.1.0.dev0"

from .handlers import setup_handlers


def _jupyter_labextension_paths():
    return [{"src": "labextension", "dest": "jupyterlab-rocm"}]


def _jupyter_server_extension_points():
    return [{"module": "jupyterlab_rocm"}]


def _load_jupyter_server_extension(server_app):
    """Register the API handlers when the Jupyter server extension loads.

    Parameters
    ----------
    server_app: jupyterlab.labapp.LabApp
        JupyterLab application instance.
    """
    setup_handlers(server_app.web_app)
    name = "jupyterlab_rocm"
    server_app.log.info(f"Registered {name} server extension")


# For backward compatibility with the classic notebook server.
_load_jupyter_server_extension = _load_jupyter_server_extension


def load_ipython_extension(ipython):
    """Register the ``%%rocprofv3`` cell magic.

    Invoked by ``%load_ext jupyterlab_rocm`` inside an IPython kernel.
    """
    from .magics import load_ipython_extension as _load

    _load(ipython)
