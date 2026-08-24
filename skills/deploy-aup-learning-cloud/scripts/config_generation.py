#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Validate cluster specifications and render deploy configuration artifacts."""

from __future__ import annotations

import ipaddress
import re

from config_common import DEFAULT_ACCEL_LABELS, HEADER_HASH, die, require, yaml_quote
from config_rendering import render_inventory, render_pxe_vars
from config_rendering import render_values as _render_values

__all__ = [
    "DEFAULT_ACCEL_LABELS",
    "HEADER_HASH",
    "AUTH_MODE_PROVIDERS",
    "SCHEMA",
    "auth_providers",
    "die",
    "render_inventory",
    "render_pxe_vars",
    "render_values",
    "require",
    "validate_accelerators",
    "validate_config_shapes",
    "validate_yaml_scalar",
    "validate_spec",
    "yaml_quote",
]

SCHEMA = {
    "topology": "pxe-diskless | ssh-preinstalled",
    "k3s_version": "v1.32.3+k3s1",
    "server": {"name": "aipc1", "ip": "192.168.0.140"},
    "agents": [{"name": "aipc2", "ip": "192.168.0.141"}],
    "network": {
        "interface": "enp1s0",
        "subnet": "192.168.0.0/24",
        "gateway": "192.168.0.1",
        "dns_servers": "8.8.8.8,8.8.4.4",
    },
    "pxe": {
        "authorized_keys": ["ssh-ed25519 AAAA... you@host"],
        "rootfs_password": "",
        "web_port": 8080,
        "diskless_agents_have_amd_gpus": True,
    },
    "accelerators": {"strix-halo": {"product_name": "AMD_Radeon_8060S_Graphics"}},
    "storage": {"class": "nfs-client"},
    "proxy": {"node_port": 30890},
    "auth_mode": "auto-login",
    "images": {"cpu": "ghcr.io/amdresearch/auplc-default:latest", "gpu": "ghcr.io/amdresearch/auplc-base:latest"},
}

HOSTNAME_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\Z"
)
K3S_VERSION_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\+k3s[0-9]+\Z")
IMAGE_KEY_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
AUTH_MODE_PROVIDERS = {
    "auto-login": ("autoLogin",),
    "dummy": ("dummy",),
    "github": ("github",),
    "local": ("native",),
    "multi": ("native", "github"),
}


def auth_providers(spec: dict) -> tuple[str, ...]:
    auth_mode = spec.get("auth_mode", "auto-login")
    if not isinstance(auth_mode, str) or auth_mode not in AUTH_MODE_PROVIDERS:
        die("spec.auth_mode must be one of: auto-login, dummy, github, local, multi")
    return AUTH_MODE_PROVIDERS[auth_mode]


def render_values(spec: dict) -> str:
    return _render_values(spec, auth_providers(spec))


def validate_accelerators(spec: dict) -> None:
    if "accelerators" not in spec:
        return
    accelerators = spec["accelerators"]
    if not isinstance(accelerators, dict):
        die("spec.accelerators must be a mapping")
    unsupported = sorted(set(accelerators) - set(DEFAULT_ACCEL_LABELS))
    if len(unsupported) == 1:
        die(f"unsupported accelerator key '{unsupported[0]}'")
    if unsupported:
        die(f"unsupported accelerator keys: {', '.join(unsupported)}")
    for key, config in accelerators.items():
        if not isinstance(config, dict):
            die(f"accelerators.{key} must be a mapping")


def validate_config_shapes(spec: dict) -> None:
    if not isinstance(spec, dict):
        die("spec must be a mapping")
    validate_accelerators(spec)
    for key in ("server", "network", "pxe", "storage", "proxy", "images"):
        if key in spec and not isinstance(spec[key], dict):
            die(f"spec.{key} must be a mapping")
    if "agents" in spec and not isinstance(spec["agents"], list):
        die("spec.agents must be a list")


def _safe_text(value, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        die(f"{path} must be a non-empty string" if not allow_empty else f"{path} must be a string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        die(f"{path} must not contain control characters")
    return value


def validate_yaml_scalar(value, path: str, *, allow_empty: bool = False) -> str:
    return _safe_text(value, path, allow_empty=allow_empty)


def _safe_hostname(value, path: str) -> str:
    hostname = _safe_text(value, path)
    if not HOSTNAME_PATTERN.fullmatch(hostname):
        die(f"{path} must be a safe hostname")
    return hostname


def _safe_ip(value, path: str) -> str:
    address = _safe_text(value, path)
    try:
        ipaddress.ip_address(address)
    except ValueError:
        die(f"{path} must be a valid IP address")
    return address


def _safe_port(value, path: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        die(f"{path} must be an integer between {minimum} and {maximum}")
    return value


def _validate_server(server: dict, path: str) -> str:
    if set(server) != {"name", "ip"}:
        die(f"{path} must contain exactly name and ip")
    name = _safe_hostname(server["name"], f"{path}.name")
    _safe_ip(server["ip"], f"{path}.ip")
    return name


def _validate_agents(spec: dict, server_name: str) -> None:
    agents = spec.get("agents", [])
    if not isinstance(agents, list):
        die("spec.agents must be a list")
    names = {server_name}
    for index, agent in enumerate(agents):
        path = f"spec.agents[{index}]"
        if not isinstance(agent, dict):
            die(f"{path} must be a mapping")
        name = _validate_server(agent, path)
        if name in names:
            die("server and agent names must be unique")
        names.add(name)


def _validate_rendered_options(spec: dict) -> None:
    auth_providers(spec)
    if "storage" in spec and "class" in spec["storage"]:
        _safe_text(spec["storage"]["class"], "spec.storage.class")
    if "proxy" in spec and "node_port" in spec["proxy"]:
        _safe_port(spec["proxy"]["node_port"], "spec.proxy.node_port", 30000, 32767)
    if "images" in spec:
        for key, value in spec["images"].items():
            if not isinstance(key, str) or not IMAGE_KEY_PATTERN.fullmatch(key):
                die("spec.images key must be a safe identifier")
            _safe_text(value, f"spec.images.{key}")
    if "accelerators" in spec:
        for key, config in spec["accelerators"].items():
            if "product_name" in config:
                _safe_text(config["product_name"], f"spec.accelerators.{key}.product_name")


def _validate_pxe(spec: dict) -> None:
    pxe = require(spec, "pxe")
    keys = pxe.get("authorized_keys")
    if not isinstance(keys, list) or not keys:
        die("pxe.authorized_keys must contain at least one SSH public key")
    for index, key in enumerate(keys):
        _safe_text(key, f"spec.pxe.authorized_keys[{index}]")
    if "rootfs_password" in pxe:
        _safe_text(pxe["rootfs_password"], "spec.pxe.rootfs_password", allow_empty=True)
    if "web_port" in pxe:
        _safe_port(pxe["web_port"], "spec.pxe.web_port", 1, 65535)
    if type(pxe.get("diskless_agents_have_amd_gpus")) is not bool:
        die("spec.pxe.diskless_agents_have_amd_gpus must be a boolean")
    network = require(spec, "network")
    _safe_text(require(spec, "network.interface"), "spec.network.interface")
    subnet = _safe_text(require(spec, "network.subnet"), "spec.network.subnet")
    try:
        ipaddress.ip_network(subnet, strict=True)
    except ValueError:
        die("spec.network.subnet must be a valid network CIDR")
    if "gateway" in network:
        _safe_ip(network["gateway"], "spec.network.gateway")
    if "dns_servers" in network:
        for index, address in enumerate(_safe_text(network["dns_servers"], "spec.network.dns_servers").split(",")):
            _safe_ip(address.strip(), f"spec.network.dns_servers[{index}]")


def validate_spec(spec: dict) -> str:
    if not isinstance(spec, dict):
        die("spec must be a mapping")
    topo = spec.get("topology")
    if topo not in ("pxe-diskless", "ssh-preinstalled"):
        die("spec.topology must be 'pxe-diskless' or 'ssh-preinstalled'")
    validate_config_shapes(spec)
    k3s_version = _safe_text(require(spec, "k3s_version"), "spec.k3s_version")
    if not K3S_VERSION_PATTERN.fullmatch(k3s_version):
        die("spec.k3s_version must be a safe k3s version")
    server_name = _validate_server(require(spec, "server"), "spec.server")
    _validate_agents(spec, server_name)
    _validate_rendered_options(spec)
    if topo == "pxe-diskless":
        _validate_pxe(spec)
    return topo
