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
Configuration Module for core

Provides a singleton HubConfig that reads configuration from a YAML file.

The YAML file is generated from values.yaml custom section (K8s) or
provided directly (standalone).

Usage:
    # In jupyterhub_config.py:
    from core.config import HubConfig
    HubConfig.init("/path/to/hub-config.yaml")

    # In business logic:
    from core.config import HubConfig
    config = HubConfig.get()
    if config.auth_mode == "multi":
        ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# =============================================================================
# YAML Configuration Models
# =============================================================================


class ResourceRequirements(BaseModel):
    """Resource requirements for a container."""

    cpu: str = "2"
    memory: str = "4Gi"
    memory_limit: str | None = None
    gpu: str | None = Field(default=None, alias="amd.com/gpu")
    npu: str | None = Field(default=None, alias="amd.com/npu")

    model_config = {"populate_by_name": True, "extra": "allow"}


class AcceleratorConfig(BaseModel):
    """Configuration for a single accelerator type."""

    displayName: str
    description: str = ""
    nodeSelector: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    quotaRate: int = 1

    model_config = {"extra": "allow"}


class QuotaSettings(BaseModel):
    """Quota system configuration."""

    enabled: bool | None = None  # None = auto-detect based on auth_mode
    cpuRate: int = 1
    minimumToStart: int = 10
    defaultQuota: int = 0

    model_config = {"extra": "allow"}


class ResourceMetadata(BaseModel):
    """Metadata for a resource (course/tutorial)."""

    group: str = "OTHERS"
    description: str = ""
    subDescription: str = ""
    accelerator: str = ""
    acceleratorKeys: list[str] = Field(default_factory=list)
    allowGitClone: bool = False

    model_config = {"extra": "allow"}


class ResourcesConfig(BaseModel):
    """Resources configuration (images, requirements, and metadata)."""

    images: dict[str, str] = Field(default_factory=dict)
    requirements: dict[str, ResourceRequirements] = Field(default_factory=dict)
    metadata: dict[str, ResourceMetadata] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class TeamsConfig(BaseModel):
    """Team to resource mapping configuration."""

    mapping: dict[str, list[str]] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class GitCloneSettings(BaseModel):
    """Git repository cloning configuration."""

    initContainerImage: str = "alpine/git:2.47.2"
    allowedProviders: list[str] = Field(default_factory=lambda: ["github.com", "gitlab.com", "bitbucket.org"])
    maxCloneTimeout: int = 300
    githubAppName: str = ""
    defaultAccessToken: str = ""

    model_config = {"extra": "allow"}


class ParsedConfig(BaseModel):
    """Parsed configuration from values.yaml custom section."""

    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    accelerators: dict[str, AcceleratorConfig] = Field(default_factory=dict)
    teams: TeamsConfig = Field(default_factory=TeamsConfig)
    quota: QuotaSettings = Field(default_factory=QuotaSettings)
    gitClone: GitCloneSettings = Field(default_factory=GitCloneSettings)

    model_config = {"extra": "allow"}

    @classmethod
    def from_dicts(
        cls,
        resources: dict | None = None,
        accelerators: dict | None = None,
        teams: dict | None = None,
        quota: dict | None = None,
        git_clone: dict | None = None,
    ) -> ParsedConfig:
        """Create configuration from individual dicts."""
        raw_config: dict[str, Any] = {}

        if resources:
            raw_config["resources"] = resources
        if accelerators:
            raw_config["accelerators"] = accelerators
        if teams:
            raw_config["teams"] = teams
        if quota:
            raw_config["quota"] = quota
        if git_clone:
            raw_config["gitClone"] = git_clone

        return cls.model_validate(raw_config)


# =============================================================================
# Hub Configuration Singleton
# =============================================================================


class HubConfig:
    """
    Singleton configuration for JupyterHub.

    All configuration comes from values.yaml via z2jh.

    Lifecycle:
        1. jupyterhub_config.py calls HubConfig.init() with config from z2jh
        2. Business logic calls HubConfig.get() to access configuration
    """

    _instance: HubConfig | None = None
    _initialized: bool = False

    def __init__(self):
        # Runtime settings
        self.auth_mode: str = "auto-login"
        self.single_node_mode: bool = False
        self.github_org_name: str = ""
        self.quota_enabled: bool = False

        # Parsed configuration
        self._config: ParsedConfig = ParsedConfig()

        # JupyterHub config object (set during setup)
        self._jupyterhub_config: Any = None

    @classmethod
    def init(cls, config_path: str | Path) -> HubConfig:
        """
        Initialize the singleton from a YAML configuration file.

        Args:
            config_path: Path to hub-config.yaml (mounted from ConfigMap or local file)

        Returns:
            The initialized HubConfig instance
        """
        if cls._instance is None:
            cls._instance = cls()

        instance = cls._instance
        config_path = Path(config_path)

        # Load configuration from YAML file
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}

        print(f"[CONFIG] Loaded configuration from {config_path}")

        # Extract runtime settings
        instance.auth_mode = raw_config.get("authMode", "auto-login")
        instance.github_org_name = raw_config.get("githubOrgName", "")

        # Single-node mode: from config or auto-enable for auto-login
        single_node_mode = raw_config.get("singleNodeMode")
        if single_node_mode is not None:
            instance.single_node_mode = single_node_mode
        else:
            instance.single_node_mode = instance.auth_mode == "auto-login"

        # Parse structured configuration
        instance._config = ParsedConfig.from_dicts(
            resources=raw_config.get("resources"),
            accelerators=raw_config.get("accelerators"),
            teams=raw_config.get("teams"),
            quota=raw_config.get("quota"),
            git_clone=raw_config.get("gitClone"),
        )

        # Quota enabled: from config or auto-detect based on auth_mode
        if instance._config.quota.enabled is not None:
            instance.quota_enabled = instance._config.quota.enabled
        else:
            # Disable quota for auto-login and dummy modes by default
            instance.quota_enabled = instance.auth_mode not in ("auto-login", "dummy")
            instance._config.quota.enabled = instance.quota_enabled

        cls._initialized = True

        # Log configuration
        print("[CONFIG] HubConfig initialized:")
        print(f"[CONFIG]   auth_mode={instance.auth_mode}")
        print(f"[CONFIG]   single_node_mode={instance.single_node_mode}")
        print(f"[CONFIG]   quota_enabled={instance.quota_enabled}")
        print(f"[CONFIG]   resources={len(instance._config.resources.images)} images")
        print(f"[CONFIG]   accelerators={list(instance._config.accelerators.keys())}")
        if instance.quota_enabled:
            print(f"[CONFIG]   quota_rates={instance.build_quota_rates()}")

        return instance

    @classmethod
    def get(cls) -> HubConfig:
        """
        Get the singleton instance.

        Raises:
            RuntimeError: If HubConfig.init() has not been called
        """
        if not cls._initialized or cls._instance is None:
            raise RuntimeError("HubConfig not initialized. Call HubConfig.init() in jupyterhub_config.py first.")
        return cls._instance

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the singleton has been initialized."""
        return cls._initialized

    # =========================================================================
    # Convenience Properties
    # =========================================================================

    @property
    def resources(self) -> ResourcesConfig:
        """Get resources configuration."""
        return self._config.resources

    @property
    def accelerators(self) -> dict[str, AcceleratorConfig]:
        """Get accelerators configuration."""
        return self._config.accelerators

    @property
    def teams(self) -> TeamsConfig:
        """Get teams configuration."""
        return self._config.teams

    @property
    def quota(self) -> QuotaSettings:
        """Get quota configuration."""
        return self._config.quota

    @property
    def git_clone(self) -> GitCloneSettings:
        """Get git clone configuration."""
        return self._config.gitClone

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_resource_image(self, resource_type: str) -> str | None:
        """Get container image for a resource type."""
        return self._config.resources.images.get(resource_type)

    def get_resource_requirements(self, resource_type: str) -> ResourceRequirements | None:
        """Get resource requirements for a resource type."""
        return self._config.resources.requirements.get(resource_type)

    def get_resource_metadata(self, resource_type: str) -> ResourceMetadata | None:
        """Get metadata for a resource type."""
        return self._config.resources.metadata.get(resource_type)

    def get_accelerator_node_selector(self, accelerator_key: str) -> dict[str, str]:
        """Get node selector for an accelerator type."""
        if accelerator_key in self._config.accelerators:
            return self._config.accelerators[accelerator_key].nodeSelector
        return {}

    def get_accelerator_env(self, accelerator_key: str) -> dict[str, str]:
        """Get environment variables for an accelerator type."""
        if accelerator_key in self._config.accelerators:
            return self._config.accelerators[accelerator_key].env
        return {}

    def get_quota_rate(self, accelerator_key: str | None) -> int:
        """Get quota rate for an accelerator type."""
        if not accelerator_key:
            return self._config.quota.cpuRate
        if accelerator_key in self._config.accelerators:
            return self._config.accelerators[accelerator_key].quotaRate
        return self._config.quota.cpuRate

    def get_team_resources(self, team: str) -> list[str]:
        """Get available resources for a team."""
        return self._config.teams.mapping.get(team, [])

    def build_quota_rates(self) -> dict[str, int]:
        """Build quota rates dict from accelerators config."""
        rates = {"cpu": self._config.quota.cpuRate}
        for key, accel in self._config.accelerators.items():
            rates[key] = accel.quotaRate
        return rates

    def build_resource_images(self) -> dict[str, str]:
        """Build resource images dict."""
        return dict(self._config.resources.images)

    def build_resource_requirements(self) -> dict[str, dict]:
        """Build resource requirements dict."""
        return {
            k: v.model_dump(by_alias=True, exclude_none=True) for k, v in self._config.resources.requirements.items()
        }

    def build_node_selector_mapping(self) -> dict[str, dict[str, str]]:
        """Build node selector mapping from accelerators."""
        return {k: v.nodeSelector for k, v in self._config.accelerators.items()}

    def build_environment_mapping(self) -> dict[str, dict[str, str]]:
        """Build environment mapping from accelerators."""
        return {k: v.env for k, v in self._config.accelerators.items()}

    def build_team_resource_mapping(self) -> dict[str, list[str]]:
        """Build team resource mapping."""
        return dict(self._config.teams.mapping)


# =============================================================================
# Legacy Compatibility
# =============================================================================

# Alias for backwards compatibility
HubCoreConfig = ParsedConfig
