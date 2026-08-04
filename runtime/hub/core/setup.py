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
JupyterHub Setup Module

This module is called from jupyterhub_config.py to set up business logic.
It reads configuration from the HubConfig singleton and configures:
- Authenticator
- Spawner
- HTTP Handlers
- API tokens
- Template paths
- Admin user auto-creation

Usage in jupyterhub_config.py:
    from core.config import HubConfig
    HubConfig.init(...)  # Initialize config singleton

    from core.setup import setup_hub
    setup_hub(c)  # Pass JupyterHub config object
"""

from __future__ import annotations

import os
from contextlib import suppress
from typing import TYPE_CHECKING, Any, TypedDict

import bcrypt

if TYPE_CHECKING:
    from core.config import AuthCapabilities


class AuthTemplateVars(TypedDict):
    auth_auto_login: bool
    auth_dummy: bool
    auth_native: bool
    auth_github: bool
    password_management_enabled: bool
    hide_logout: bool


def _build_auth_template_vars(auth: AuthCapabilities) -> AuthTemplateVars:
    auth.validate()
    return {
        "auth_auto_login": auth.auto_login,
        "auth_dummy": auth.dummy,
        "auth_native": auth.native,
        "auth_github": auth.github,
        "password_management_enabled": auth.native,
        "hide_logout": auth.auto_login,
    }


def _bootstrap_admin_password(admin_username: str, admin_password: str) -> None:
    from core.authenticators.models import UserPassword
    from core.database import session_scope

    created = False
    with session_scope() as session:
        user_pw = session.query(UserPassword).filter_by(username=admin_username).first()
        if user_pw is None:
            password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt())
            session.add(
                UserPassword(
                    username=admin_username,
                    password_hash=password_hash,
                    force_change=False,
                )
            )
            created = True

    if created:
        print(f"[SETUP] Admin '{admin_username}' password set automatically")
    else:
        print(f"[SETUP] Admin '{admin_username}' password already set")


def _configure_api_token(c: Any, api_token: str | None, admin_username: str) -> None:
    if api_token:
        c.JupyterHub.api_tokens = {api_token: admin_username}
        print(f"[SETUP] API token loaded for administrator '{admin_username}'")


def setup_hub(c: Any) -> None:
    """
    Set up JupyterHub with business logic from core.

    This function:
    1. Gets configuration from HubConfig singleton
    2. Configures the spawner class
    3. Configures the authenticator class
    4. Registers HTTP handlers
    5. Sets up quota session cleanup

    Args:
        c: JupyterHub configuration object (from get_config())
    """
    from core import z2jh
    from core.authenticators import (
        GITHUB_USERNAME_PREFIX,
        CustomFirstUseAuthenticator,
        CustomGitHubOAuthenticator,
        create_authenticator,
    )
    from core.config import HubConfig
    from core.database import create_all_tables, init_database
    from core.handlers import configure_handlers, get_handlers
    from core.metrics_updater import start_metrics_updater
    from core.spawner import RemoteLabKubeSpawner

    # Get the initialized config singleton
    config = HubConfig.get()
    auth = config.auth
    github_app_id = ""
    github_app_installation_id = ""
    github_app_private_key = ""
    github_app_private_key_file = ""
    github_team_sync_ttl_seconds = 3600
    if auth.github:
        github_app_id = z2jh.get_config("hub.config.GitHubOAuthenticator.app_id", "")
        github_app_installation_id = z2jh.get_config("hub.config.GitHubOAuthenticator.installation_id", "")
        github_app_private_key = z2jh.get_config("hub.config.GitHubOAuthenticator.private_key", "")
        github_app_private_key_file = z2jh.get_config("hub.config.GitHubOAuthenticator.private_key_file", "")
        github_team_sync_ttl_seconds = z2jh.get_config("hub.config.GitHubOAuthenticator.team_sync_ttl_seconds", 3600)

    # =========================================================================
    # Configure Spawner
    # =========================================================================

    # Configure spawner class with all settings from config (single entry point)
    RemoteLabKubeSpawner.configure_from_config(config)

    c.JupyterHub.spawner_class = RemoteLabKubeSpawner

    # Start background metrics updater after hub event loop is ready
    import asyncio

    def _start_metrics_updater():
        with suppress(Exception):
            start_metrics_updater()

    loop = asyncio.get_event_loop()
    loop.call_later(5, _start_metrics_updater)

    # =========================================================================
    # Pre-create System Groups
    # =========================================================================
    # Ensure system-managed groups exist at startup (before any user logs in).
    # Note: load_groups does NOT set properties on existing groups, so the
    # source=system backfill is handled lazily in the admin groups API handler.
    c.JupyterHub.load_groups = {}
    if auth.native:
        c.JupyterHub.load_groups["native-users"] = []
    if auth.github:
        c.JupyterHub.load_groups["github-users"] = []

    # =========================================================================
    # Configure Authenticator
    # =========================================================================

    c.Authenticator.enable_auth_state = True
    c.Authenticator.auth_refresh_age = 3600  # check token refresh every hour

    async def auth_state_hook(spawner, auth_state):
        if auth_state is None:
            spawner.github_access_token = None
            # Still assign native users to their default group
            if auth.native and not spawner.user.name.startswith(GITHUB_USERNAME_PREFIX):
                try:
                    from core.groups import assign_user_to_group

                    assign_user_to_group(spawner.user, "native-users", spawner.user.db)
                except Exception as e:
                    print(f"[GROUPS] Warning: Failed to assign native user group for {spawner.user.name}: {e}")
            return
        spawner.github_access_token = auth_state.get("access_token")

        if auth.github and spawner.user.name.startswith(GITHUB_USERNAME_PREFIX):
            try:
                from core.groups import sync_github_teams_for_user

                synced = await sync_github_teams_for_user(
                    spawner.user,
                    github_app_id,
                    github_app_installation_id,
                    github_app_private_key,
                    github_app_private_key_file,
                    config.github_org_name,
                    set(config.teams.mapping.keys()),
                    spawner.user.db,
                    team_sync_ttl_seconds=github_team_sync_ttl_seconds,
                )
                if not synced:
                    print(
                        f"[GROUPS] GitHub team sync unavailable for {spawner.user.name}; keeping existing team groups"
                    )
            except Exception as e:
                print(f"[GROUPS] Warning: Failed to sync GitHub teams for {spawner.user.name}: {e}")

            # Assign all GitHub users to default group (fallback for users without teams)
            try:
                from core.groups import assign_user_to_group

                assign_user_to_group(spawner.user, "github-users", spawner.user.db)
            except Exception as e:
                print(f"[GROUPS] Warning: Failed to assign github-users group for {spawner.user.name}: {e}")
        elif auth.native and not spawner.user.name.startswith(GITHUB_USERNAME_PREFIX):
            # Native user with auth_state but no GitHub teams
            try:
                from core.groups import assign_user_to_group

                assign_user_to_group(spawner.user, "native-users", spawner.user.db)
            except Exception as e:
                print(f"[GROUPS] Warning: Failed to assign native user group for {spawner.user.name}: {e}")

    c.Spawner.auth_state_hook = auth_state_hook

    c.JupyterHub.authenticator_class = create_authenticator(auth)

    if auth.auto_login or (auth.native and not auth.github):
        c.Authenticator.allow_all = True
    if auth.native and auth.github:
        c.MultiAuthenticator.authenticators = [
            {
                "authenticator_class": CustomGitHubOAuthenticator,
                "url_prefix": "/github",
            },
            {
                "authenticator_class": CustomFirstUseAuthenticator,
                "url_prefix": "/native",
                "config": {"prefix": "", "allow_all": True},
            },
        ]

    # =========================================================================
    # Configure Handlers
    # =========================================================================

    configure_handlers(
        accelerator_options={k: v.model_dump() for k, v in config.accelerators.items()},
        quota_rates=config.build_quota_rates(),
        quota_enabled=config.quota_enabled,
        minimum_quota_to_start=config.quota.minimumToStart,
        default_quota=config.quota.defaultQuota,
        team_resource_mapping=dict(config.teams.mapping),
        github_org=config.github_org_name,
        platform_name=config.platform_display_name,
    )

    if not hasattr(c.JupyterHub, "extra_handlers") or c.JupyterHub.extra_handlers is None:
        c.JupyterHub.extra_handlers = []

    for route, handler in get_handlers():
        c.JupyterHub.extra_handlers.append((route, handler))

    # =========================================================================
    # Protect GitHub-synced groups in native JupyterHub API
    # =========================================================================
    #
    # JupyterHub registers its own /api/groups/* handlers in default_handlers
    # BEFORE extra_handlers, so extra_handlers cannot override them (Tornado
    # matches first-registered route first). We replace the handler classes
    # in-place within the default_handlers list so that the native routes
    # point to our protected subclasses.

    from jupyterhub.apihandlers import default_handlers as _api_default_handlers
    from jupyterhub.apihandlers.groups import (
        GroupAPIHandler as _OrigGroupAPI,
    )
    from jupyterhub.apihandlers.groups import (
        GroupUsersAPIHandler as _OrigGroupUsersAPI,
    )
    from tornado import web

    from core.groups import is_readonly_group as _is_readonly
    from core.groups import is_undeletable_group as _is_undeletable

    class _ProtectedGroupAPIHandler(_OrigGroupAPI):
        def delete(self, group_name):
            group = self.find_group(group_name)
            if _is_undeletable(group):
                raise web.HTTPError(403, "Cannot delete a protected group")
            return super().delete(group_name)

    class _ProtectedGroupUsersAPIHandler(_OrigGroupUsersAPI):
        def post(self, group_name):
            group = self.find_group(group_name)
            if _is_readonly(group):
                raise web.HTTPError(403, "Cannot modify members of a protected group")
            return super().post(group_name)

        async def delete(self, group_name):
            group = self.find_group(group_name)
            if _is_readonly(group):
                raise web.HTTPError(403, "Cannot modify members of a protected group")
            return await super().delete(group_name)

    _replacements = {
        _OrigGroupAPI: _ProtectedGroupAPIHandler,
        _OrigGroupUsersAPI: _ProtectedGroupUsersAPIHandler,
    }

    for i, (route, handler) in enumerate(_api_default_handlers):
        if handler in _replacements:
            _api_default_handlers[i] = (route, _replacements[handler])

    print("[SETUP] Protected GitHub-synced groups in native JupyterHub API")

    # =========================================================================
    # Determine Database URL
    # =========================================================================

    db_type = z2jh.get_config("hub.db.type", "sqlite-pvc")
    if db_type == "sqlite-pvc":
        db_url = "sqlite:////srv/jupyterhub/jupyterhub.sqlite"
    elif db_type == "sqlite-memory":
        db_url = "sqlite://"
    else:
        # PostgreSQL or MySQL - get URL from config
        db_url = z2jh.get_config("hub.db.url", "sqlite:////srv/jupyterhub/jupyterhub.sqlite")

    # =========================================================================
    # Initialize Shared Database
    # =========================================================================

    init_database(db_url)

    create_all_tables()

    # =========================================================================
    # Run Auth Migration
    # =========================================================================

    try:
        from core.authenticators.migrate import check_migration_needed as auth_migration_needed
        from core.authenticators.migrate import migrate_auth_data

        if auth_migration_needed():
            print("[AUTH] Migrating data from old DBM files...")
            migrate_auth_data(db_url)

    except Exception as e:
        print(f"[AUTH] Warning: Failed to run auth migration: {e}")

    # =========================================================================
    # Initialize Quota Manager
    # =========================================================================

    # Always initialize QuotaManager for session tracking (regardless of quota_enabled)
    try:
        from core.quota import init_quota_manager

        quota_manager = init_quota_manager()
        stale_sessions = quota_manager.cleanup_stale_sessions()
        if stale_sessions:
            print(f"[QUOTA] Cleaned up {len(stale_sessions)} stale sessions on startup")
        active_count = quota_manager.get_active_sessions_count()
        print(f"[QUOTA] {active_count} active sessions found")
    except Exception as e:
        print(f"[QUOTA] Warning: Failed to initialize quota manager: {e}")

    if config.quota_enabled:
        try:
            from core.quota.migrate import check_migration_needed, migrate_quota_data

            if check_migration_needed():
                print("[QUOTA] Migrating data from old quota.sqlite...")
                migrate_quota_data(db_url)
        except Exception as e:
            print(f"[QUOTA] Warning: Failed to run quota migration: {e}")

    # =========================================================================
    # Auto-Create Admin User
    # =========================================================================

    admin_password = os.environ.get("JUPYTERHUB_ADMIN_PASSWORD", "")
    admin_username = os.environ.get("JUPYTERHUB_ADMIN_USERNAME", "admin")
    api_token = os.environ.get("JUPYTERHUB_API_TOKEN")

    if admin_password and not auth.native:
        raise RuntimeError("Administrator password bootstrap requires native authentication")

    if admin_password:
        try:
            _bootstrap_admin_password(admin_username, admin_password)
        except Exception as e:
            raise RuntimeError("Failed to bootstrap administrator credentials") from e

    _configure_api_token(c, api_token, admin_username)

    if admin_password:
        c.Authenticator.admin_users = {admin_username}
        print(f"[SETUP] Admin user configured: {admin_username}")

    # =========================================================================
    # Template Paths
    # =========================================================================

    template_path = os.environ.get("JUPYTERHUB_TEMPLATE_PATH", "/tmp/custom_templates")
    c.JupyterHub.template_paths = [template_path]

    # =========================================================================
    # Template Vars
    # =========================================================================

    if not isinstance(c.JupyterHub.template_vars, dict):
        c.JupyterHub.template_vars = {}
    c.JupyterHub.template_vars.update(_build_auth_template_vars(auth))
    c.JupyterHub.template_vars["cluster_name"] = config.cluster_name  # type: ignore[assignment]
    c.JupyterHub.template_vars["platform_name"] = config.platform_display_name  # type: ignore[assignment]

    print(
        "[SETUP] Hub setup complete: auth="
        f"auto_login:{auth.auto_login},dummy:{auth.dummy},native:{auth.native},github:{auth.github}"
    )
    print(f"[SETUP] template_vars: {c.JupyterHub.template_vars}")
