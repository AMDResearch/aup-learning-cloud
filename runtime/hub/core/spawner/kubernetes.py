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

"""
Kubernetes Spawner Implementation

Provides RemoteLabKubeSpawner for Kubernetes-based deployments.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import copy
import json
import os
import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlparse

from jupyterhub.user import User as JupyterHubUser
from kubespawner import KubeSpawner
from tornado import web

from core.metrics import (
    pod_failure_total,
    repo_clone_failed_total,
    session_runtime_minutes,
    spawn_duration_seconds,
    spawn_failed_total,
    spawn_gpu_total,
)

if TYPE_CHECKING:
    from core.config import HubConfig


# NPU Security Config
# Special security config to enable `sudo` when using NPU inside docker.
NPU_SECURITY_CONFIG = {
    "extra_container_config": {
        "securityContext": {
            "allowPrivilegeEscalation": True,
            "privileged": True,
            "capabilities": {"add": ["IPC_LOCK", "SYS_ADMIN"]},
        }
    }
}

LEGACY_CODE_SERVER_RESOURCES = {"code-cpu", "code-gpu"}
DEFAULT_LAUNCH_MODE = "jupyterlab"
CODE_SERVER_LAUNCH_MODE = "code-server"
DEFAULT_TARGET_PATH = "/home/jovyan"


class RemoteLabKubeSpawner(KubeSpawner):
    """
    KubeSpawner implementation for RemoteLab.

    Provides:
    - Team-based resource access control
    - GPU/NPU selection and node affinity
    - Quota integration for usage tracking
    - Automatic container shutdown
    """

    # Type annotation to override KubeSpawner's MockObject type
    user: JupyterHubUser  # type: ignore[assignment]

    # Configuration injection (set by factory)
    _hub_config: HubConfig | None = None

    # Runtime settings (set by jupyterhub_config.py)
    github_org_name: str = ""
    auth_mode: str = "auto-login"
    single_node_mode: bool = False
    quota_enabled: bool | None = False

    # Resource configuration (set from config)
    resource_images: dict[str, str] = {}
    resource_requirements: dict[str, dict] = {}
    accelerator_options: dict[str, dict] = {}
    team_resource_mapping: dict[str, list[str]] = {}
    node_selector_mapping: dict[str, dict[str, str]] = {}
    environment_mapping: dict[str, dict[str, str]] = {}

    # Quota settings
    quota_rates: dict[str, int] = {}
    default_quota: int = 0
    minimum_quota_to_start: int = 10

    # Repository cloning configuration (populated from HubConfig.git_clone)
    ALLOWED_GIT_PROVIDERS: set[str] = set()
    MAX_CLONE_TIMEOUT: int = 0
    GIT_INIT_CONTAINER_IMAGE: str = ""
    GITHUB_APP_NAME: str = ""
    DEFAULT_ACCESS_TOKEN: bool = False
    DEFAULT_ACCESS_TOKEN_SECRET: str = "jupyterhub-git-default-token"

    # Allowed origins for notebook server WebSocket connections
    notebook_allowed_origins: list[str] = []

    # Extra domains trusted by code-server's outgoing link protection.
    code_server_extra_trusted_domains: list[str] = []

    @classmethod
    def configure_from_config(cls, config: HubConfig) -> None:
        """
        Configure the spawner class from a HubCoreConfig instance.

        This should be called during initialization to inject configuration.
        """
        cls._hub_config = config

        # Basic spawner settings
        cls.auth_mode = config.auth_mode
        cls.single_node_mode = config.single_node_mode
        cls.github_org_name = config.github_org_name

        # Extract resource images and requirements
        cls.resource_images = dict(config.resources.images)
        cls.resource_requirements = {
            k: v.model_dump(by_alias=True, exclude_none=True) for k, v in config.resources.requirements.items()
        }

        # Extract accelerator configuration
        cls.accelerator_options = {k: v.model_dump() for k, v in config.accelerators.items()}
        cls.node_selector_mapping = {k: v.nodeSelector for k, v in config.accelerators.items()}
        cls.environment_mapping = {k: v.env for k, v in config.accelerators.items()}

        # Extract team mapping
        cls.team_resource_mapping = dict(config.teams.mapping)

        # Extract quota settings
        cls.quota_rates = config.build_quota_rates()
        cls.default_quota = config.quota.defaultQuota
        cls.minimum_quota_to_start = config.quota.minimumToStart
        cls.quota_enabled = config.quota.enabled

        # Extract git clone settings (single source of truth: GitCloneSettings)
        git_config = config.git_clone
        cls.GIT_INIT_CONTAINER_IMAGE = git_config.initContainerImage
        cls.ALLOWED_GIT_PROVIDERS = set(git_config.allowedProviders)
        cls.MAX_CLONE_TIMEOUT = git_config.maxCloneTimeout
        cls.GITHUB_APP_NAME = git_config.githubAppName
        cls.DEFAULT_ACCESS_TOKEN = bool(git_config.defaultAccessToken)

        # Extract singleuser allowed origins
        cls.notebook_allowed_origins = list(config.notebook_network.allowedOrigins)

        # Extract code-server link protection settings
        cls.code_server_extra_trusted_domains = list(config.code_server.extraTrustedDomains)

    async def get_user_resources(self) -> list[str]:
        """Get available resources for the user based on their JupyterHub group memberships.

        For auto-login/dummy modes, returns all configured resources.
        For all other users, resolves resources from JupyterHub groups
        (which are synced from GitHub teams or assigned to native users
        via the auth_state_hook). Falls back to legacy pattern matching
        for native users with no group assignments.

        Returns:
            List of resource names the user can access
        """
        username = self.user.name.strip()
        self.log.debug(f"Resolving resources for user: {username}")

        from core.groups import resolve_resources_for_user

        available_resources = resolve_resources_for_user(
            self.user,
            self.team_resource_mapping,
            self.auth_mode,
            list(self.resource_images.keys()),
        )
        self.log.debug(f"User '{username}' resolved resources: {available_resources}")
        return available_resources

    async def options_form(self, _) -> str:
        """Generate the HTML form for resource selection.

        Returns a <script> tag that injects ``window.AVAILABLE_RESOURCES``
        and ``window.SINGLE_NODE_MODE`` for the React spawn app.  The custom
        ``spawn.html`` template renders this via ``{{ spawner_options_form | safe }}``.
        """
        try:
            available_resource_names = await self.get_user_resources()
            self.log.debug(f"Providing users with following resources: {available_resource_names}")

            available_resources_js = json.dumps(available_resource_names)
            single_node_mode_js = "true" if self.single_node_mode else "false"

            return (
                "<script>"
                f"window.AVAILABLE_RESOURCES={available_resources_js};"
                f"window.SINGLE_NODE_MODE={single_node_mode_js};"
                "</script>"
            )

        except Exception as e:
            self.log.error(f"Failed to load options form: {e}", exc_info=True)
            return """
            <div style="padding: 20px; background: #ffebee; border: 1px solid #f44336; border-radius: 8px; color: #c62828;">
                <strong>Error:</strong> Failed to load resource selection form.
                <br>Please contact an administrator or check the server logs.
            </div>
            """

    def _generate_fallback_form(self, available_resource_names: list[str]) -> str:
        """Generate a simple fallback form if template is not available."""
        options_html = ""

        for i, resource_name in enumerate(available_resource_names):
            if resource_name in self.resource_images:
                requirements = self.resource_requirements.get(resource_name, {})
                cpu = requirements.get("cpu", "2")
                memory = requirements.get("memory", "4Gi").replace("Gi", "GB")

                checked = "checked" if i == 0 else ""

                options_html += f"""
                <div style="margin-bottom: 12px; padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px; background: white;">
                    <label style="display: flex; align-items: center; cursor: pointer;">
                        <input type="radio" name="resource_type" value="{resource_name}" {checked}
                               style="margin-right: 12px;">
                        <div>
                            <strong>{resource_name.upper()}</strong>
                            <div style="font-size: 0.9em; color: #666;">
                                {cpu} CPU, {memory} Memory
                            </div>
                        </div>
                    </label>
                </div>
                """

        if not options_html:
            options_html = """
            <div style="padding: 20px; background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; color: #856404;">
                <strong>No resources available</strong><br>
                Please contact administrator for access.
            </div>
            """

        return f"""
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h3>Choose a Resource</h3>
            {options_html}
            <div style="margin-top: 20px;">
                <label for="runtime">Run my server for (minutes):</label>
                <input name="runtime" type="number" min="10" value="20" max="120" step="5"
                       style="margin-left: 10px; padding: 8px; width: 80px;">
            </div>
            <div style="margin-top: 20px;">
                <input type="submit" value="Start" class="btn btn-jupyter form-control">
            </div>
        </div>
        """

    def options_from_form(self, formdata) -> dict[str, Any]:
        """Parse form data and configure the spawner based on selected resource and GPU."""
        options = {}

        # Parse runtime
        runtime_minutes = formdata.get("runtime", ["20"])[0]
        options["runtime_minutes"] = int(runtime_minutes)

        # Parse resource type
        resource_type_list = formdata.get("resource_type", [])
        if len(resource_type_list) != 1:
            raise RuntimeError(f"Selected 0 or more than 1 resources! {resource_type_list}")

        resource_type = resource_type_list[0]
        options["resource_type"] = resource_type

        # Parse GPU selection if available
        gpu_selection = formdata.get(f"gpu_selection_{resource_type}", [None])[0]
        options["gpu_selection"] = gpu_selection

        # Validate resource type
        if resource_type not in self.resource_images:
            raise RuntimeError(f"Unknown Resource: {resource_type}")

        # Configure spawner based on selections
        self._configure_spawner(resource_type, gpu_selection)

        self.log.debug(
            f"User selected resource: {resource_type} with GPU: {gpu_selection} for {runtime_minutes} minutes"
        )

        # Optional repository cloning fields (do not break existing forms)
        try:
            repo_url = formdata.get("repo_url", [""])[0].strip()
        except Exception:
            repo_url = ""

        try:
            repo_branch = formdata.get("repo_branch", [""])[0].strip()
        except Exception:
            repo_branch = ""

        if repo_url:
            options["repo_url"] = repo_url
            options["repo_persist"] = self._resolve_repo_persist_option(formdata)
        if repo_branch:
            options["repo_branch"] = repo_branch

        return options

    def _resolve_repo_persist_option(self, formdata) -> bool:
        git_config = self._hub_config.git_clone if self._hub_config else None
        allow_choice = bool(getattr(git_config, "allowPersistenceChoice", False))
        default_persistence = bool(getattr(git_config, "defaultPersistence", True))

        if not allow_choice:
            return default_persistence

        try:
            raw_value = formdata.get("repo_persist", [None])[0]
        except Exception:
            raw_value = None

        if isinstance(raw_value, str):
            normalized_value = raw_value.strip().lower()
            if normalized_value == "true":
                return True
            if normalized_value == "false":
                return False

        return default_persistence

    def _get_public_hub_home_url(self) -> str:
        """Return the public Hub home URL for links opened from code-server."""
        hub_path = "/hub/home"
        handler = getattr(self, "handler", None)

        if handler is None:
            return hub_path

        public_url = str(getattr(handler, "public_url", "") or "").strip()
        if public_url:
            parsed = urlparse(public_url)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return public_url.rstrip("/") + hub_path

        request = getattr(handler, "request", None)
        protocol = str(getattr(request, "protocol", "") or "").strip()
        host = str(getattr(request, "host", "") or "").strip()
        if protocol in {"http", "https"} and host:
            return f"{protocol}://{host}{hub_path}"

        return hub_path

    @staticmethod
    def _trusted_domain_from_url(url: str) -> str | None:
        """Extract a code-server trusted-domain host from an absolute URL."""

        try:
            parsed = urlparse(str(url).strip())
        except Exception:
            return None

        if parsed.scheme not in {"http", "https"}:
            return None
        return (parsed.hostname or "").strip().lower() or None

    @staticmethod
    def _normalize_code_server_trusted_domain(domain: str) -> str | None:
        """Normalize a configured code-server trusted domain entry."""

        value = str(domain).strip().lower()
        if not value:
            return None

        # Administrators should provide host/domain patterns, not full URLs.
        if "://" in value or "/" in value or "\x00" in value or any(char.isspace() for char in value):
            return None
        if value in {"*", "*."}:
            return None

        return value

    def _get_code_server_trusted_domains(self, hub_url: str) -> str:
        """Return comma-separated domains trusted by code-server link protection."""

        domains: list[str] = []
        auto_domain = self._trusted_domain_from_url(hub_url)
        if auto_domain:
            domains.append(auto_domain)

        domains.extend(self.code_server_extra_trusted_domains)

        normalized_domains: list[str] = []
        for domain in domains:
            normalized = self._normalize_code_server_trusted_domain(domain)
            if normalized and normalized not in normalized_domains:
                normalized_domains.append(normalized)

        return ",".join(normalized_domains)

    def _validate_and_sanitize_repo_url(self, url: str) -> tuple[bool, str, str]:
        """
        Validate and normalize a repository URL.
        Returns (is_valid, error_message, sanitized_url).
        Empty/blank URLs return (True, "", "").

        Normalization applied (mirrors frontend logic):
        - Prepends https:// if no scheme present
        - Strips /tree/<branch> path component
        - Strips trailing .git suffix
        """
        if not url or not str(url).strip():
            return True, "", ""

        url = str(url).strip()

        # Prepend https:// if no scheme
        if "://" not in url:
            url = "https://" + url

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ["http", "https"]:
                return False, "Only HTTP/HTTPS URLs supported", ""
            if not parsed.netloc:
                return False, "Invalid URL format", ""

            path = parsed.path

            # Strip /tree/<branch> path component
            tree_match = re.match(r"^(/[^/]+/[^/]+)/tree/.+$", path)
            if tree_match:
                path = tree_match.group(1)

            # Strip .git suffix
            if path.endswith(".git"):
                path = path[:-4]

            # Reconstruct without query/fragment
            from urllib.parse import urlunparse

            url = urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

            hostname = parsed.netloc.lower()
            is_whitelisted = any(
                hostname == provider or hostname.endswith("." + provider) for provider in self.ALLOWED_GIT_PROVIDERS
            )
            if not is_whitelisted:
                return False, f"Repository host '{hostname}' not authorized", ""

        except Exception as e:
            return False, f"URL parsing error: {e}", ""

        dangerous_patterns = [";", "||", "&&", "$(", "`", "\n", "\r"]
        if any(pat in url for pat in dangerous_patterns):
            return False, "URL contains suspicious characters", ""

        return True, "", url

    def _extract_repo_name(self, url: str) -> str:
        """Extract and sanitize a directory name from a git repo URL."""
        path = urlparse(url).path.rstrip("/")
        name = path.split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        name = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
        return name or "repo"

    def _get_home_mount_path(self, home_volume_name: str) -> str:
        """Return the mountPath of the home volume from self.volume_mounts."""
        for vm in self.volume_mounts:
            if vm.get("name") == home_volume_name:
                return vm["mountPath"]
        return DEFAULT_TARGET_PATH

    @staticmethod
    def _jupyterlab_tree_url_for_target_path(target_path: str) -> str:
        """Map an absolute container path to a JupyterLab tree URL."""
        path_without_leading_slash = target_path.lstrip("/")
        return f"/lab/tree/{quote(path_without_leading_slash, safe='/')}"

    def _resolve_target_path(self, resource_type: str, custom_repo_path: str | None = None) -> str | None:
        """Resolve the effective landing path for the selected launch target."""
        if custom_repo_path:
            return custom_repo_path

        resource_metadata = self._hub_config.get_resource_metadata(resource_type) if self._hub_config else None
        default_path = str(getattr(resource_metadata, "defaultPath", "") or "").strip()

        # defaultPath is a Hub launch-dir override, not the image WORKDIR.
        # If it is omitted, preserve the image/application default instead of
        # guessing a path; this keeps non-standard images in their own WORKDIR.
        return default_path or None

    def _apply_target_path_mapping(self, resource_type: str, target_path: str | None) -> None:
        """Apply the effective target path to the selected single-user adapter."""
        if not target_path:
            return

        if self._launches_code_server(resource_type):
            # Hub Spawner.default_url becomes JUPYTERHUB_DEFAULT_URL for single-user servers.
            # Hub spawn-pending redirects browsers to the server base URL, and code-server
            # does not consume JUPYTERHUB_DEFAULT_URL. Direct ?folder= URLs work, but spawn
            # completion does not deliver them, so AUPLC_CODE_WORKDIR is the reliable adapter.
            self.environment["AUPLC_CODE_WORKDIR"] = target_path
        else:
            self.notebook_dir = "/"
            self.default_url = self._jupyterlab_tree_url_for_target_path(target_path)

    async def _create_git_token_secret(self, access_token: str) -> str:
        """Create a K8s Secret containing the git access token.

        The Secret is bound to the user pod via ownerReferences so it
        is automatically garbage-collected when the pod is deleted.
        """
        import secrets as _secrets

        from kubernetes_asyncio import client as k8s_client
        from kubernetes_asyncio.client import ApiClient

        safe_username = re.sub(r"[^a-z0-9-]", "-", self.user.name.lower())[:40]
        suffix = _secrets.token_hex(3)
        secret_name = f"git-token-{safe_username}-{suffix}"

        secret = k8s_client.V1Secret(
            metadata=k8s_client.V1ObjectMeta(
                name=secret_name,
                namespace=self.namespace,
                labels={
                    "component": "git-token",
                    "heritage": "jupyterhub",
                    "app.kubernetes.io/managed-by": "jupyterhub",
                    "hub.jupyter.org/username": safe_username,
                },
            ),
            string_data={"token": access_token},
            type="Opaque",
        )

        async with ApiClient() as api_client:
            v1 = k8s_client.CoreV1Api(api_client)
            await v1.create_namespaced_secret(self.namespace, secret)
        self.log.info(f"Created git token secret {secret_name} for user {self.user.name}")
        return secret_name

    async def _cleanup_git_token_secrets(self) -> None:
        """Clean up any leftover git token secrets for this user."""
        try:
            from kubernetes_asyncio import client as k8s_client
            from kubernetes_asyncio.client import ApiClient

            safe_username = re.sub(r"[^a-z0-9-]", "-", self.user.name.lower())[:40]
            label_selector = f"component=git-token,hub.jupyter.org/username={safe_username}"
            async with ApiClient() as api_client:
                v1 = k8s_client.CoreV1Api(api_client)
                secrets = await v1.list_namespaced_secret(self.namespace, label_selector=label_selector)
                for secret in secrets.items:
                    try:
                        await v1.delete_namespaced_secret(secret.metadata.name, self.namespace)
                        self.log.info(f"Cleaned up git token secret {secret.metadata.name}")
                    except Exception:
                        pass
        except Exception as e:
            self.log.warning(f"Failed to cleanup git token secrets: {e}")

    async def _build_git_init_container(
        self,
        repo_url: str,
        repo_name: str,
        home_volume_name: str,
        home_mount_path: str,
        repo_persist: bool,
        repo_branch: str = "",
        access_token: str = "",
    ) -> dict:
        """
        Build an init container spec that clones a repository into the home mount path.

        The init container mounts the same home PVC as the main container and clones
        into <home_mount_path>/<repo_name>. In ephemeral mode, a preStop lifecycle hook
        on the main container removes the directory when the session ends.

        The script is read from core/scripts/git-clone.sh, base64-encoded and decoded
        at runtime to prevent KubeSpawner's _expand_all from treating shell braces as
        Python format string placeholders. Variables are passed as environment variables.
        """
        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "git-clone.sh")
        with open(script_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()

        clone_dir = f"{home_mount_path}/{repo_name}"
        metadata_dir = f"{home_mount_path}/.auplc/git-clones"

        env: list[dict[str, Any]] = [
            {"name": "REPO_URL", "value": repo_url},
            {"name": "CLONE_DIR", "value": clone_dir},
            {"name": "PERSIST_CLONED_REPO", "value": "true" if repo_persist else "false"},
            {"name": "AUPLC_GIT_METADATA_DIR", "value": metadata_dir},
            {"name": "MAX_CLONE_TIMEOUT", "value": str(self.MAX_CLONE_TIMEOUT)},
        ]
        if repo_branch:
            env.append({"name": "BRANCH", "value": repo_branch})

        if access_token:
            secret_name = await self._create_git_token_secret(access_token)
            env.append(
                {
                    "name": "GIT_ACCESS_TOKEN",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": secret_name,
                            "key": "token",
                        }
                    },
                }
            )
        elif self.DEFAULT_ACCESS_TOKEN:
            env.append(
                {
                    "name": "GIT_ACCESS_TOKEN",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": self.DEFAULT_ACCESS_TOKEN_SECRET,
                            "key": "token",
                        }
                    },
                }
            )

        return {
            "name": "init-clone-repo",
            "image": self.GIT_INIT_CONTAINER_IMAGE,
            "imagePullPolicy": "IfNotPresent",
            "command": ["sh", "-c", f"echo {encoded} | base64 -d | sh"],
            "env": env,
            "volumeMounts": [{"name": home_volume_name, "mountPath": home_mount_path}],
            "securityContext": {
                "runAsUser": 1000,
                "runAsNonRoot": True,
                "allowPrivilegeEscalation": False,
            },
            "resources": {
                "requests": {"memory": "128Mi", "cpu": "100m"},
                "limits": {"memory": "256Mi", "cpu": "300m"},
            },
        }

    def _parse_memory_string(self, memory_str) -> float:
        """Parse memory string with units like '16Gi' or '512Mi' to float in GB."""
        if isinstance(memory_str, (int, float)):
            return float(memory_str)

        memory_str = str(memory_str).strip()

        if memory_str.isdigit():
            return float(memory_str)

        units = {
            "Ki": 1 / 1024 / 1024,
            "Mi": 1 / 1024,
            "Gi": 1,
            "Ti": 1024,
            "K": 1 / 1000 / 1000,
            "M": 1 / 1000,
            "G": 1,
            "T": 1000,
        }

        for unit, multiplier in units.items():
            if memory_str.endswith(unit):
                try:
                    value = float(memory_str[: -len(unit)])
                    return value * multiplier
                except ValueError:
                    pass

        try:
            return float(memory_str)
        except ValueError:
            print(f"Warning: Could not parse memory value '{memory_str}', defaulting to 1GB")
            return 1.0

    def get_quota_rate(self, accelerator_type: str | None) -> int:
        """Get quota rate based on accelerator type."""
        if not accelerator_type:
            return self.quota_rates.get("cpu", 1)
        return self.quota_rates.get(accelerator_type, self.quota_rates.get("cpu", 1))

    @staticmethod
    def _build_runtime_metadata_env(
        *,
        start_time: int,
        runtime_minutes: int,
        quota_rate: int,
        runtime_unlimited: bool,
    ) -> dict[str, str]:
        env = {
            "JOB_START_TIME": str(start_time),
            "QUOTA_RATE": str(quota_rate),
        }

        if runtime_unlimited:
            env["AUPLC_RUNTIME_UNLIMITED"] = "true"
        else:
            env["JOB_RUN_TIME"] = str(runtime_minutes)

        return env

    @staticmethod
    def _with_ephemeral_clone_cleanup(extra_container_config: dict | None, clone_dir: str) -> dict:
        extra = copy.deepcopy(extra_container_config or {})
        lifecycle = extra.setdefault("lifecycle", {})
        lifecycle["preStop"] = {"exec": {"command": ["rm", "-rf", clone_dir]}}
        return extra

    def _get_launch_mode(self, resource_type: str) -> str:
        """Return the configured launch mode for a resource."""
        resource_metadata = self._hub_config.get_resource_metadata(resource_type) if self._hub_config else None
        launch_mode = str(getattr(resource_metadata, "launchMode", "") or "").strip().lower()
        if launch_mode:
            return launch_mode
        if resource_type in LEGACY_CODE_SERVER_RESOURCES:
            return CODE_SERVER_LAUNCH_MODE
        return DEFAULT_LAUNCH_MODE

    def _launches_code_server(self, resource_type: str) -> bool:
        """Return whether the resource should launch code-server directly."""
        return self._get_launch_mode(resource_type) == CODE_SERVER_LAUNCH_MODE

    def _reset_per_spawn_state(self) -> None:
        """Clear fields that are derived from the selected resource each spawn."""
        if not hasattr(self, "_resource_baseline_state"):
            self._resource_baseline_state = {
                "cmd": copy.deepcopy(self.cmd),
                "args": copy.deepcopy(self.args),
                "default_url": copy.deepcopy(self.default_url),
                "node_affinity_required": copy.deepcopy(self.node_affinity_required),
                "extra_resource_guarantees": copy.deepcopy(self.extra_resource_guarantees),
                "extra_resource_limits": copy.deepcopy(self.extra_resource_limits),
                "init_containers": copy.deepcopy(self.init_containers),
                "extra_container_config": copy.deepcopy(self.extra_container_config),
                "environment": copy.deepcopy(self.environment),
            }

        for key, value in self._resource_baseline_state.items():
            setattr(self, key, copy.deepcopy(value))

        self._has_git_init_container = False

    def _configure_spawner(self, resource_type: str, gpu_selection: str | None = None) -> None:
        """Configure the spawner based on the resource type and GPU selection."""

        self._reset_per_spawn_state()

        # Set basic configuration
        self.image = self.resource_images[resource_type]

        # Override image based on accelerator selection
        if gpu_selection and self._hub_config:
            metadata = self._hub_config.get_resource_metadata(resource_type)
            if metadata and metadata.acceleratorOverrides:
                accel_override = metadata.acceleratorOverrides.get(gpu_selection)
                if accel_override and accel_override.image:
                    self.log.info(
                        f"Image override for {resource_type}/{gpu_selection}: {self.image} -> {accel_override.image}"
                    )
                    self.image = accel_override.image

        # Set resource requirements
        requirements = self.resource_requirements[resource_type]

        # Set CPU guarantee and limit
        self.cpu_guarantee = float(requirements["cpu"])
        self.cpu_limit = float(requirements["cpu"]) * 1.25  # Add 25% buffer

        # Handle memory values
        memory_str = requirements["memory"]

        if memory_str.endswith("Gi"):
            numeric_part = float(memory_str[:-2])
            self.mem_guarantee = f"{numeric_part}G"
        else:
            self.mem_guarantee = memory_str

        # Handle memory limit
        if "memory_limit" in requirements:
            limit_str = requirements["memory_limit"]
            if limit_str.endswith("Gi"):
                limit_numeric = float(limit_str[:-2])
                self.mem_limit = f"{limit_numeric}G"
            else:
                self.mem_limit = limit_str
        else:
            if memory_str.endswith("Gi"):
                numeric_part = float(memory_str[:-2])
                limit_value = numeric_part * 1.5
                self.mem_limit = f"{limit_value}G"
            else:
                try:
                    match = re.match(r"^([\d.]+)", memory_str)
                    if match:
                        numeric_part = float(match.group(1))
                        limit_value = numeric_part * 1.5
                        self.mem_limit = f"{limit_value}G"
                    else:
                        self.mem_limit = memory_str
                except Exception:
                    self.mem_limit = memory_str

        # GPU/NPU resources
        if "amd.com/gpu" in requirements:
            self.extra_resource_guarantees = {"amd.com/gpu": str(requirements["amd.com/gpu"])}
            self.extra_resource_limits = {"amd.com/gpu": str(requirements["amd.com/gpu"])}
        elif "amd.com/npu" in requirements:
            self.log.debug("NPU DEVICE PLUGIN are removed, amd.com/npu is no more needed")

        # Configure node affinity based on GPU selection
        if gpu_selection and gpu_selection in self.node_selector_mapping:
            node_selector = self.node_selector_mapping[gpu_selection]

            node_affinity = {
                "matchExpressions": [
                    {"key": key, "operator": "In", "values": [value]} for key, value in node_selector.items()
                ]
            }

            self.node_affinity_required = [node_affinity]
            self.log.debug(f"Set node affinity for GPU {gpu_selection}: {node_affinity}")

            # Set environment variables from accelerator config
            if gpu_selection in self.environment_mapping:
                env_vars = self.environment_mapping[gpu_selection]
                if env_vars:
                    self.environment.update(env_vars)
                    self.log.debug(f"Set environment variables: {env_vars}")

        # Apply per-resource env overrides (can override or unset accelerator vars)
        if self._hub_config:
            resource_meta = self._hub_config.get_resource_metadata(resource_type)
            if resource_meta:
                # Resource-level env (applies to all accelerators)
                if resource_meta.env:
                    for key, value in resource_meta.env.items():
                        if value == "":
                            self.environment.pop(key, None)
                        else:
                            self.environment[key] = value
                    self.log.debug(f"Applied per-resource env for {resource_type}: {resource_meta.env}")

                # Per-accelerator env override (highest priority)
                if gpu_selection and resource_meta.acceleratorOverrides:
                    accel_override = resource_meta.acceleratorOverrides.get(gpu_selection)
                    if accel_override and accel_override.env:
                        for key, value in accel_override.env.items():
                            if value == "":
                                self.environment.pop(key, None)
                            else:
                                self.environment[key] = value
                        self.log.debug(
                            f"Applied acceleratorOverrides env for {resource_type}/{gpu_selection}: {accel_override.env}"
                        )

        if self._launches_code_server(resource_type):
            self.cmd = ["/usr/local/bin/start-code-server.sh"]
            self.args = []
            self.environment["AUPLC_HUB_URL"] = "/hub/home"
            self.environment["AUPLC_LAUNCH_MODE"] = CODE_SERVER_LAUNCH_MODE

        # Special configuration for NPU resources
        if resource_type in ["Tutorial-NPU-Resnet", "ROSCON2025-GPU", "ROSCON2025-NPU"]:
            self.log.debug(f"Set node affinity for NPU {resource_type}")
            for key, value in NPU_SECURITY_CONFIG.items():
                if hasattr(self, key):
                    setattr(self, key, value)

            self.cmd = ["/bin/bash", "-l", "-c", "jupyterhub-singleuser", "--allow-root"]

    async def start(self):
        """Start the spawner and schedule automatic shutdown."""
        # Ensure pod fails immediately (not retried) when an init container fails.
        # JupyterHub manages pod lifecycle; Kubernetes should not silently restart pods.
        self.extra_pod_config["restartPolicy"] = "Never"

        runtime_minutes = self.user_options.get("runtime_minutes", 20)
        resource_type = self.user_options.get("resource_type", "cpu")
        gpu_selection = self.user_options.get("gpu_selection", None)
        username = self.user.name.lower()

        # Determine accelerator type for quota calculation
        accelerator_type = gpu_selection if gpu_selection else "cpu"

        # Prometheus metric: spawn attempt
        with contextlib.suppress(Exception):
            spawn_gpu_total.labels(accelerator=accelerator_type).inc()

        from core.quota import get_quota_manager

        quota_manager = get_quota_manager()

        # Always start a usage session for tracking, regardless of quota state
        self.usage_session_id = quota_manager.start_usage_session(username, resource_type, accelerator_type)

        # Quota check (if enabled)
        if self.quota_enabled:
            # Check if user has unlimited quota
            has_unlimited = quota_manager.is_unlimited_in_db(username)

            if has_unlimited:
                print(f"[QUOTA] User {username} has unlimited quota, skipping quota check")
                self._has_unlimited_quota = True
            else:
                can_start, message, estimated_cost = quota_manager.can_start_container(
                    username,
                    accelerator_type,
                    runtime_minutes,
                    self.quota_rates,
                    self.default_quota,
                )

                if not can_start:
                    print(f"[QUOTA] Blocked container start for {username}: {message}")
                    with contextlib.suppress(Exception):
                        spawn_failed_total.labels(reason="quota").inc()
                    raise web.HTTPError(
                        403,
                        f"Cannot start container: {message}. Please contact administrator to add quota.",
                    )

                self._has_unlimited_quota = False
                print(
                    f"[QUOTA] Session {self.usage_session_id} started for {username} ({accelerator_type}), estimated cost: {estimated_cost}"
                )
        else:
            self._has_unlimited_quota = True

        start_time = int(time.time())

        # Track spawn start time for metrics
        self._spawn_start_timestamp = time.time()

        # Calculate quota rate for this accelerator type
        quota_rate = self.get_quota_rate(accelerator_type) if self.quota_enabled else 0

        # Set environment variables for runtime display extensions.
        for key in ("JOB_START_TIME", "JOB_RUN_TIME", "QUOTA_RATE", "AUPLC_RUNTIME_UNLIMITED"):
            self.environment.pop(key, None)
        self.environment.update(
            self._build_runtime_metadata_env(
                start_time=start_time,
                runtime_minutes=runtime_minutes,
                quota_rate=quota_rate,
                runtime_unlimited=self.single_node_mode,
            )
        )

        launches_code_server = self._launches_code_server(resource_type)

        if launches_code_server:
            hub_url = self._get_public_hub_home_url()
            self.environment["AUPLC_HUB_URL"] = hub_url
            trusted_domains = self._get_code_server_trusted_domains(hub_url)
            if trusted_domains:
                self.environment["AUPLC_CODE_TRUSTED_DOMAINS"] = trusted_domains
            else:
                self.environment.pop("AUPLC_CODE_TRUSTED_DOMAINS", None)

        # Inject allowed origins into notebook server startup args
        if self.notebook_allowed_origins and not launches_code_server:
            origin_pat = "|".join(re.escape(o) if o != "*" else ".*" for o in self.notebook_allowed_origins)
            extra_args = list(self.args or [])
            extra_args += [
                f"--ServerApp.allow_origin_pat={origin_pat}",
            ]
            if "*" in self.notebook_allowed_origins:
                extra_args.append("--ServerApp.allow_origin=*")
            self.args = extra_args

        # Prefer a repo URL provided by the frontend only; do not fallback to config
        try:
            repo_url = str(self.user_options.get("repo_url", "") or "").strip()
            repo_branch = str(self.user_options.get("repo_branch", "") or "").strip()
        except Exception:
            repo_url = ""
            repo_branch = ""

        # Token fallback: OAuth token (GitHub App) > default token secret
        access_token = ""
        try:
            auth_state = await self.user.get_auth_state()
            if auth_state and auth_state.get("access_token") and self.GITHUB_APP_NAME:
                access_token = auth_state["access_token"]
        except Exception:
            pass

        # Check if the selected resource permits git cloning
        resource_type = self.user_options.get("resource_type", "")
        resource_metadata = self._hub_config.get_resource_metadata(resource_type) if self._hub_config else None
        allow_git_clone = resource_metadata.allowGitClone if resource_metadata else False

        if repo_url and not allow_git_clone:
            self.log.warning(
                f"Repository URL ignored for user {self.user.name}: "
                f"resource '{resource_type}' does not allow git cloning"
            )
            repo_url = ""

        # Extract branch from URL path if not provided separately (e.g. /owner/repo/tree/main)
        if repo_url and not repo_branch:
            tree_match = re.match(r"^https?://[^/]+/[^/]+/[^/]+/tree/(.+)$", repo_url)
            if tree_match:
                repo_branch = tree_match.group(1)

        # Sanitize branch name: allow only safe characters
        if repo_branch and not re.match(r"^[a-zA-Z0-9_./-]+$", repo_branch):
            self.log.warning(f"Invalid branch name for user {self.user.name}: {repo_branch!r}")
            repo_branch = ""

        custom_repo_path = None

        if repo_url:
            is_valid, err_msg, sanitized_url = self._validate_and_sanitize_repo_url(repo_url)
            if not is_valid:
                self.log.warning(f"Repository URL rejected for user {self.user.name}: {err_msg}")
            else:
                try:
                    repo_name = self._extract_repo_name(sanitized_url)

                    safe_username = self._expand_user_properties("{username}")
                    home_volume_name = f"volume-{safe_username}"
                    home_mount_path = self._get_home_mount_path(home_volume_name)
                    repo_persist = bool(self.user_options.get("repo_persist", True))
                    init_container = await self._build_git_init_container(
                        sanitized_url,
                        repo_name,
                        home_volume_name,
                        home_mount_path,
                        repo_persist,
                        repo_branch,
                        access_token,
                    )
                    self.init_containers = [init_container] + list(self.init_containers or [])

                    clone_dir = f"{home_mount_path}/{repo_name}"
                    custom_repo_path = clone_dir
                    if not repo_persist:
                        self.extra_container_config = self._with_ephemeral_clone_cleanup(
                            self.extra_container_config,
                            clone_dir,
                        )

                    self._has_git_init_container = True
                    branch_info = f" (branch: {repo_branch})" if repo_branch else ""
                    self.log.info(
                        f"Configured git init container for {self.user.name}: {sanitized_url} -> ~/{repo_name}{branch_info}"
                    )
                except Exception as e:
                    self.log.warning(f"Failed to configure git init container: {e}")

        target_path = self._resolve_target_path(resource_type, custom_repo_path)
        self._apply_target_path_mapping(resource_type, target_path)

        if getattr(self, "_has_git_init_container", False):
            ref_key = f"{self.namespace}/{self.pod_name}"
            start_task = asyncio.ensure_future(super().start())
            monitor_task = asyncio.ensure_future(self._monitor_pod_failure(ref_key))
            try:
                done, pending = await asyncio.wait(
                    {start_task, monitor_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                if monitor_task in done and not monitor_task.cancelled():
                    monitor_task.result()  # re-raises failure RuntimeError
                start_result = start_task.result()

                # Record spawn duration metric
                try:
                    if hasattr(self, "_spawn_start_timestamp"):
                        duration = time.time() - self._spawn_start_timestamp
                        spawn_duration_seconds.observe(duration)
                        accelerator_type = self.user_options.get("gpu_selection") or "cpu"
                        # active session count is derived from quota manager, not inc/dec
                except Exception:
                    pass
            except Exception:
                with contextlib.suppress(Exception):
                    await self.stop(True)
                raise
        else:
            start_result = await super().start()

        # Store for internal use
        self.start_time = start_time
        self._resource_type = resource_type

        # In single-node mode, skip auto-shutdown timer
        if self.single_node_mode:
            self.shutdown_time = None
            self.check_timer = None
            self.log.debug(f"Container for {self.user.name} started (single-node mode, no time limit)")
        else:
            self.shutdown_time = start_time + (runtime_minutes * 60)
            loop = asyncio.get_event_loop()
            self.check_timer = loop.call_later(60, self.check_timeout)
            self.log.debug(f"Container for {self.user.name} started at {time.ctime(self.start_time)}")
            self.log.debug(f"Scheduled shutdown after {runtime_minutes} minutes at {time.ctime(self.shutdown_time)}")

        return start_result

    async def _monitor_pod_failure(self, ref_key: str) -> None:
        """Raise immediately if the pod enters Failed phase.

        Runs concurrently with super().start() so that a failed init container
        (e.g. git clone error) is detected without waiting for start_timeout.
        """
        seen_running = False
        while True:
            await asyncio.sleep(3)
            reflector = getattr(self, "pod_reflector", None)
            if reflector is None:
                continue
            pod = reflector.pods.get(ref_key)
            if pod is None:
                continue
            phase = pod["status"]["phase"]
            # Wait until the pod has moved past Pending at least once,
            # so we don't react to a stale Failed status from a previous pod.
            if phase in ("Running", "Pending"):
                seen_running = True
                continue
            if phase == "Failed" and seen_running:
                try:
                    pod_failure_total.labels(reason="git_clone_failed").inc()
                    repo_clone_failed_total.inc()
                except Exception:
                    pass

                raise RuntimeError(
                    "Server failed to start: the Git repository could not be cloned. "
                    "Verify the URL is correct and the repository is publicly accessible."
                )

    async def stop(self, now=False):
        """Stop the container and record quota usage."""
        # Clean up any leftover git token secrets
        await self._cleanup_git_token_secrets()

        username = self.user.name
        try:
            from core.quota import get_quota_manager

            quota_manager = get_quota_manager()
            quota_rates = self.quota_rates if self.quota_enabled else None

            session_id = getattr(self, "usage_session_id", None)
            self.usage_session_id = None

            if session_id:
                duration, quota_used = quota_manager.end_usage_session(session_id, quota_rates)
                print(f"[USAGE] Session ended for {username}. Duration: {duration} min, Quota used: {quota_used}")
            else:
                # Hub may have restarted and lost in-memory session id — find and close any active session for this user
                active = quota_manager.get_active_session(username)
                if active:
                    duration, quota_used = quota_manager.end_usage_session(active["session_id"], quota_rates)
                    print(
                        f"[USAGE] Recovered session for {username}. Duration: {duration} min, Quota used: {quota_used}"
                    )
        except Exception as e:
            print(f"[USAGE] Error ending session for {username}: {e}")

        if hasattr(self, "check_timer") and self.check_timer:
            with contextlib.suppress(Exception):
                self.check_timer.cancel()

        try:
            start_ts = getattr(self, "_spawn_start_timestamp", None)

            if start_ts:
                runtime_minutes = max(0, (time.time() - start_ts) / 60.0)
                session_runtime_minutes.observe(runtime_minutes)

            # active session metric is derived from quota manager state
        except Exception:
            pass

        return await super().stop(now=now)

    def check_timeout(self) -> None:
        """Periodic check for container timeout."""
        if self.shutdown_time is None:
            return

        current_time = time.time()

        if current_time >= self.shutdown_time:
            self.log.debug(
                f"Stopping container for user {self.user.name} as requested time has elapsed at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
            )
            asyncio.ensure_future(self.stop())
        else:
            loop = asyncio.get_event_loop()
            self.check_timer = loop.call_later(60, self.check_timeout)

            remaining_minutes = int((self.shutdown_time - current_time) / 60)
            if remaining_minutes % 5 == 0:
                self.log.debug(
                    f"Container for {self.user.name} has {remaining_minutes} minutes remaining at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                )
