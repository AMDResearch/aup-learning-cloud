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
JupyterHub Configuration - Main Entry Point

This file is installed in the Docker image and loaded by JupyterHub.
All configuration is read from Helm values.yaml via z2jh.
"""

from __future__ import annotations

import glob
import os
import re
from typing import TYPE_CHECKING, Any

from kubernetes_asyncio import client
from tornado.httpclient import AsyncHTTPClient

from core import z2jh
from core.config import HubConfig
from core.setup import setup_hub

if TYPE_CHECKING:
    from traitlets.config import Config

    def get_config() -> Config: ...

# =============================================================================
# Initialize HubConfig Singleton
# =============================================================================

# Load configuration from mounted YAML file (generated from values.yaml custom section)
HUB_CONFIG_PATH = "/usr/local/etc/jupyterhub/config/hub-config.yaml"

HubConfig.init(config_path=HUB_CONFIG_PATH)

# =============================================================================
# Setup Business Logic
# =============================================================================

c = get_config()  # noqa: F821

setup_hub(c)

# =============================================================================
# Z2JH Standard Configuration (Kubernetes-specific)
# =============================================================================


def _camel_case(s: str) -> str:
    return re.sub(r"_([a-z])", lambda m: m.group(1).upper(), s)


# Custom template path
c.JupyterHub.template_paths = ["/tmp/custom_templates"]

# Use curl backend for HTTP requests
AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")

# Proxy configuration
c.ConfigurableHTTPProxy.api_url = (
    f"http://{z2jh.get_name('proxy-api')}:{z2jh.get_name_env('proxy-api', '_SERVICE_PORT')}"
)
c.ConfigurableHTTPProxy.should_start = False

# Hub settings
c.JupyterHub.cleanup_servers = False
c.JupyterHub.last_activity_interval = 60

# Base tornado settings — always applied.
# Security note: 'unsafe-inline' is required because JupyterHub injects inline
# scripts (e.g. darkmode observer) and Cloudflare Bot Fight also injects inline
# JS that cannot be predicted ahead of time. Removing 'unsafe-inline' would
# require nonce support coordinated across Hub and Cloudflare, tracked as a
# future hardening task. This policy still prevents loading scripts/resources
# from arbitrary external origins, which is the primary CSP risk.
_BASE_TORNADO_SETTINGS: dict = {
    "slow_spawn_timeout": 0,
    "headers": {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "report-uri /hub/security/csp-report"
        ),
        # Platform attribution — survives frontend rewrites because it is set
        # at the Tornado application layer, not in any template or React component.
        "X-Powered-By": "AUP Learning Cloud",
    },
}

# Hub allowed origins: merge CORS header into tornado_settings without clobbering.
_hub_config = HubConfig.get()
_hub_allowed_origins = _hub_config.hub_network.allowedOrigins
if _hub_allowed_origins:
    _origin_val = "*" if "*" in _hub_allowed_origins else ", ".join(_hub_allowed_origins)
    _BASE_TORNADO_SETTINGS.setdefault("headers", {})["Access-Control-Allow-Origin"] = _origin_val
    print(f"[CONFIG] Hub allowedOrigins: {_hub_allowed_origins}")

c.JupyterHub.tornado_settings = _BASE_TORNADO_SETTINGS

# Harden _xsrf session cookie via Tornado's xsrf_cookie_kwargs.
# JupyterHub.cookie_options only affects Hub session cookies; the _xsrf cookie
# is managed directly by Tornado and requires xsrf_cookie_kwargs in
# tornado_settings to set Secure and SameSite.
#
# Secure is conditional: browsers reject Secure cookies received over HTTP
# (RFC 6265 §5.4) for non-loopback origins, which would break POST /hub/spawn
# on the default `auplc-installer install` (NodePort + HTTP). Set Secure only
# when the public origin actually uses HTTPS:
#   - proxy.https.enabled=true   -> chart terminates TLS itself (autohttps)
#   - custom.security.publicScheme="https" -> opt-in for external TLS
#     terminators (Cloudflare tunnel, external HTTPS ingress / LB)
# SameSite=Lax is always safe and blocks cross-site POST CSRF while still
# allowing OAuth top-level redirects.
# HttpOnly is intentionally omitted: JupyterHub's frontend JS must read
# _xsrf to include it in form submissions.
_proxy_https_enabled = bool(z2jh.get_config("proxy.https.enabled", False))
_public_scheme = str(z2jh.get_config("custom.security.publicScheme") or "").strip().lower()
_use_secure_cookies = _proxy_https_enabled or _public_scheme == "https"

_xsrf_cookie_kwargs: dict = {"samesite": "Lax"}
if _use_secure_cookies:
    _xsrf_cookie_kwargs["secure"] = True

c.JupyterHub.tornado_settings = {
    **c.JupyterHub.tornado_settings,
    "xsrf_cookie_kwargs": _xsrf_cookie_kwargs,
}

# Inject platform identity into every Jinja template context so that
# {{ powered_by }} is available in all Hub-rendered pages.
c.JupyterHub.template_vars = {"powered_by": "AUP Learning Cloud"}

# Database configuration
db_type = z2jh.get_config("hub.db.type")
if db_type == "sqlite-pvc":
    c.JupyterHub.db_url = "sqlite:///jupyterhub.sqlite"
elif db_type == "sqlite-memory":
    c.JupyterHub.db_url = "sqlite://"
else:
    z2jh.set_config_if_not_none(c.JupyterHub, "db_url", "hub.db.url")

db_password = z2jh.get_secret_value("hub.db.password", None)
if db_password is not None:
    if db_type == "mysql":
        os.environ["MYSQL_PWD"] = db_password
    elif db_type == "postgres":
        os.environ["PGPASSWORD"] = db_password

# Hub traits from values.yaml
for trait, cfg_key in (
    ("concurrent_spawn_limit", None),
    ("active_server_limit", None),
    ("base_url", None),
    ("allow_named_servers", None),
    ("named_server_limit_per_user", None),
    ("redirect_to_server", None),
    ("shutdown_on_logout", None),
    ("template_vars", None),
):
    if cfg_key is None:
        cfg_key = _camel_case(trait)

    # Special handling for template_vars - merge instead of overwrite
    if trait == "template_vars":
        value = z2jh.get_config("hub." + cfg_key)
        if value is not None:
            if not isinstance(c.JupyterHub.template_vars, dict):
                c.JupyterHub.template_vars = {}
            c.JupyterHub.template_vars.update(value)
    else:
        z2jh.set_config_if_not_none(c.JupyterHub, trait, "hub." + cfg_key)

# Optional Prometheus metrics access
metrics_enabled = z2jh.get_config("monitoring.hubMetrics.enabled", False)
allow_unauthenticated_metrics = z2jh.get_config("monitoring.hubMetrics.allowUnauthenticatedScrape", False)

if metrics_enabled and allow_unauthenticated_metrics:
    c.JupyterHub.authenticate_prometheus = False

# Hub bind and connect URLs
hub_container_port = 8081
c.JupyterHub.hub_bind_url = f"http://:{hub_container_port}"
c.JupyterHub.hub_connect_url = f"http://{z2jh.get_name('hub')}:{z2jh.get_name_env('hub', '_SERVICE_PORT')}"

# =============================================================================
# KubeSpawner Configuration
# =============================================================================

# Common labels
common_labels = c.KubeSpawner.common_labels = {}
common_labels["app.kubernetes.io/name"] = common_labels["app"] = z2jh.get_config(
    "nameOverride", default=z2jh.get_config("Chart.Name", "jupyterhub")
)
release = z2jh.get_config("Release.Name")
if release:
    common_labels["app.kubernetes.io/instance"] = common_labels["release"] = release
chart_name = z2jh.get_config("Chart.Name")
chart_version = z2jh.get_config("Chart.Version")
if chart_name and chart_version:
    common_labels["helm.sh/chart"] = common_labels["chart"] = f"{chart_name}-{chart_version.replace('+', '_')}"
common_labels["app.kubernetes.io/managed-by"] = "kubespawner"

c.KubeSpawner.namespace = os.environ.get("POD_NAMESPACE", "default")

z2jh.set_config_if_not_none(c.Spawner, "consecutive_failure_limit", "hub.consecutiveFailureLimit")

for trait, cfg_key in (
    ("pod_name_template", None),
    ("start_timeout", None),
    ("image_pull_policy", "image.pullPolicy"),
    ("events_enabled", "events"),
    ("extra_labels", None),
    ("extra_annotations", None),
    ("uid", None),
    ("fs_gid", None),
    ("service_account", "serviceAccountName"),
    ("storage_extra_labels", "storage.extraLabels"),
    ("node_selector", None),
    ("node_affinity_required", "extraNodeAffinity.required"),
    ("node_affinity_preferred", "extraNodeAffinity.preferred"),
    ("pod_affinity_required", "extraPodAffinity.required"),
    ("pod_affinity_preferred", "extraPodAffinity.preferred"),
    ("pod_anti_affinity_required", "extraPodAntiAffinity.required"),
    ("pod_anti_affinity_preferred", "extraPodAntiAffinity.preferred"),
    ("lifecycle_hooks", None),
    ("init_containers", None),
    ("extra_containers", None),
    ("mem_limit", "memory.limit"),
    ("mem_guarantee", "memory.guarantee"),
    ("cpu_limit", "cpu.limit"),
    ("cpu_guarantee", "cpu.guarantee"),
    ("environment", "extraEnv"),
    ("profile_list", None),
    ("extra_pod_config", None),
):
    if cfg_key is None:
        cfg_key = _camel_case(trait)
    z2jh.set_config_if_not_none(c.KubeSpawner, trait, "singleuser." + cfg_key)

c.KubeSpawner.allow_privilege_escalation = z2jh.get_config("singleuser.allowPrivilegeEscalation")

# Image pull secrets
image_pull_secrets: list[str] = []
if z2jh.get_config("imagePullSecret.automaticReferenceInjection") and z2jh.get_config("imagePullSecret.create"):
    image_pull_secrets.append(z2jh.get_name("image-pull-secret"))
if z2jh.get_config("imagePullSecrets"):
    image_pull_secrets.extend(z2jh.get_config_list("imagePullSecrets"))
if z2jh.get_config("singleuser.image.pullSecrets"):
    image_pull_secrets.extend(z2jh.get_config_list("singleuser.image.pullSecrets"))
if image_pull_secrets:
    c.KubeSpawner.image_pull_secrets = image_pull_secrets

# Scheduling
if z2jh.get_config("scheduling.userScheduler.enabled"):
    c.KubeSpawner.scheduler_name = z2jh.get_name("user-scheduler")
if z2jh.get_config("scheduling.podPriority.enabled"):
    c.KubeSpawner.priority_class_name = z2jh.get_name("priority")

# Node affinity
match_node_purpose = z2jh.get_config("scheduling.userPods.nodeAffinity.matchNodePurpose")
if match_node_purpose:
    node_selector = {
        "matchExpressions": [{"key": "hub.jupyter.org/node-purpose", "operator": "In", "values": ["user"]}]
    }
    if match_node_purpose == "prefer":
        c.KubeSpawner.node_affinity_preferred.append({"weight": 100, "preference": node_selector})
    elif match_node_purpose == "require":
        c.KubeSpawner.node_affinity_required.append(node_selector)

# Tolerations
scheduling_user_pods_tolerations = z2jh.get_config_list("scheduling.userPods.tolerations")
singleuser_extra_tolerations = z2jh.get_config_list("singleuser.extraTolerations")
tolerations = scheduling_user_pods_tolerations + singleuser_extra_tolerations
if tolerations:
    c.KubeSpawner.tolerations = tolerations

# Storage configuration
storage_type = z2jh.get_config("singleuser.storage.type")
if storage_type == "dynamic":
    pvc_name_template = z2jh.get_config("singleuser.storage.dynamic.pvcNameTemplate")
    if pvc_name_template:
        c.KubeSpawner.pvc_name_template = pvc_name_template
    volume_name_template = z2jh.get_config("singleuser.storage.dynamic.volumeNameTemplate")
    c.KubeSpawner.storage_pvc_ensure = True
    z2jh.set_config_if_not_none(c.KubeSpawner, "storage_class", "singleuser.storage.dynamic.storageClass")
    z2jh.set_config_if_not_none(c.KubeSpawner, "storage_access_modes", "singleuser.storage.dynamic.storageAccessModes")
    z2jh.set_config_if_not_none(c.KubeSpawner, "storage_capacity", "singleuser.storage.capacity")

    c.KubeSpawner.volumes = [{"name": volume_name_template, "persistentVolumeClaim": {"claimName": "{pvc_name}"}}]
    c.KubeSpawner.volume_mounts = [
        {
            "mountPath": z2jh.get_config("singleuser.storage.homeMountPath"),
            "name": volume_name_template,
            "subPath": z2jh.get_config("singleuser.storage.dynamic.subPath"),
        }
    ]
elif storage_type == "static":
    pvc_claim_name = z2jh.get_config("singleuser.storage.static.pvcName")
    c.KubeSpawner.volumes = [{"name": "home", "persistentVolumeClaim": {"claimName": pvc_claim_name}}]
    c.KubeSpawner.volume_mounts = [
        {
            "mountPath": z2jh.get_config("singleuser.storage.homeMountPath"),
            "name": "home",
            "subPath": z2jh.get_config("singleuser.storage.static.subPath"),
        }
    ]

# Extra files
extra_files = z2jh.get_config_dict("singleuser.extraFiles")
if extra_files:
    volume: dict[str, Any] = {"name": "files"}
    items = []
    for file_key, file_details in extra_files.items():
        item: dict[str, Any] = {"key": file_key, "path": file_key}
        if "mode" in file_details:
            item["mode"] = file_details["mode"]
        items.append(item)
    volume["secret"] = {"secretName": z2jh.get_name("singleuser"), "items": items}
    c.KubeSpawner.volumes.append(volume)

    volume_mounts = []
    for file_key, file_details in extra_files.items():
        volume_mounts.append({"mountPath": file_details["mountPath"], "subPath": file_key, "name": "files"})
    c.KubeSpawner.volume_mounts.extend(volume_mounts)

# Extra volumes
c.KubeSpawner.volumes.extend(z2jh.get_config_list("singleuser.storage.extraVolumes"))
c.KubeSpawner.volume_mounts.extend(z2jh.get_config_list("singleuser.storage.extraVolumeMounts"))

# =============================================================================
# Services and Roles
# =============================================================================

c.JupyterHub.services = []
c.JupyterHub.load_roles = []

# Idle culler
if z2jh.get_config("cull.enabled", False):
    from jupyterhub.utils import url_path_join

    jupyterhub_idle_culler_role: dict[str, Any] = {
        "name": "jupyterhub-idle-culler",
        "scopes": ["list:users", "read:users:activity", "read:servers", "delete:servers"],
        "services": ["jupyterhub-idle-culler"],
    }

    cull_cmd = ["python3", "-m", "jupyterhub_idle_culler"]
    base_url = c.JupyterHub.get("base_url", "/")
    cull_cmd.append("--url=http://localhost:8081" + url_path_join(base_url, "hub/api"))

    cull_timeout = z2jh.get_config("cull.timeout")
    if cull_timeout:
        cull_cmd.append(f"--timeout={cull_timeout}")

    cull_every = z2jh.get_config("cull.every")
    if cull_every:
        cull_cmd.append(f"--cull-every={cull_every}")

    cull_concurrency = z2jh.get_config("cull.concurrency")
    if cull_concurrency:
        cull_cmd.append(f"--concurrency={cull_concurrency}")

    if z2jh.get_config("cull.users"):
        cull_cmd.append("--cull-users")
        jupyterhub_idle_culler_role["scopes"].append("admin:users")

    if not z2jh.get_config("cull.adminUsers"):
        cull_cmd.append("--cull-admin-users=false")

    if z2jh.get_config("cull.removeNamedServers"):
        cull_cmd.append("--remove-named-servers")

    cull_max_age = z2jh.get_config("cull.maxAge")
    if cull_max_age:
        cull_cmd.append(f"--max-age={cull_max_age}")

    c.JupyterHub.services.append({"name": "jupyterhub-idle-culler", "command": cull_cmd})
    c.JupyterHub.load_roles.append(jupyterhub_idle_culler_role)

# Additional services from values.yaml
for key, service in z2jh.get_config("hub.services", {}).items():
    service.setdefault("name", key)
    service.pop("apiToken", None)
    service["api_token"] = z2jh.get_secret_value(f"hub.services.{key}.apiToken")
    c.JupyterHub.services.append(service)

for key, role in z2jh.get_config("hub.loadRoles", {}).items():
    role.setdefault("name", key)
    c.JupyterHub.load_roles.append(role)

z2jh.set_config_if_not_none(c.Spawner, "default_url", "singleuser.defaultUrl")

# Cloud metadata blocking
cloud_metadata = z2jh.get_config("singleuser.cloudMetadata")
if cloud_metadata and cloud_metadata.get("blockWithIptables"):
    network_tools_image_name = z2jh.get_config("singleuser.networkTools.image.name")
    network_tools_image_tag = z2jh.get_config("singleuser.networkTools.image.tag")
    network_tools_resources = z2jh.get_config("singleuser.networkTools.resources")
    ip = cloud_metadata["ip"]
    ip_block_container = client.V1Container(
        name="block-cloud-metadata",
        image=f"{network_tools_image_name}:{network_tools_image_tag}",
        command=[
            "iptables",
            "--append",
            "OUTPUT",
            "--protocol",
            "tcp",
            "--destination",
            ip,
            "--destination-port",
            "80",
            "--jump",
            "DROP",
        ],
        security_context=client.V1SecurityContext(
            privileged=True, run_as_user=0, capabilities=client.V1Capabilities(add=["NET_ADMIN"])
        ),
        resources=network_tools_resources,
    )
    c.KubeSpawner.init_containers.append(ip_block_container)

# Debug mode
if z2jh.get_config("debug.enabled", False):
    c.JupyterHub.log_level = "DEBUG"
    c.Spawner.debug = True

# Secrets
c.JupyterHub.cookie_secret = z2jh.get_secret_value("hub.config.JupyterHub.cookie_secret")
_crypt_keys = z2jh.get_secret_value("hub.config.CryptKeeper.keys")
if _crypt_keys is not None:
    c.CryptKeeper.keys = _crypt_keys.split(";")

# Hub config from values.yaml
for app, cfg in z2jh.get_config("hub.config", {}).items():
    if app == "JupyterHub":
        cfg.pop("proxy_auth_token", None)
        cfg.pop("cookie_secret", None)
        cfg.pop("services", None)
        cfg.pop("authenticator_class", None)
    elif app == "ConfigurableHTTPProxy":
        cfg.pop("auth_token", None)
    elif app == "CryptKeeper":
        cfg.pop("keys", None)
    c[app].update(cfg)

# Load additional config files
extra_config_dir = "/usr/local/etc/jupyterhub/jupyterhub_config.d"
if os.path.isdir(extra_config_dir):
    for file_path in sorted(glob.glob(f"{extra_config_dir}/*.py")):
        file_name = os.path.basename(file_path)
        print(f"Loading {extra_config_dir} config: {file_name}")
        with open(file_path) as f:
            file_content = f.read()
        exec(compile(source=file_content, filename=file_name, mode="exec"))

# Extra config from values.yaml
for key, config_py in sorted(z2jh.get_config("hub.extraConfig", {}).items()):
    print(f"Loading extra config: {key}")
    exec(config_py)
