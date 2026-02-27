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
from typing import TYPE_CHECKING, Any

import bcrypt

if TYPE_CHECKING:
    pass


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
    from core.authenticators import (
        CustomFirstUseAuthenticator,
        CustomGitHubOAuthenticator,
        create_authenticator,
    )
    from core.config import HubConfig
    from core.database import create_all_tables, init_database
    from core.handlers import configure_handlers, get_handlers
    from core.spawner import RemoteLabKubeSpawner

    # Get the initialized config singleton
    config = HubConfig.get()

    # =========================================================================
    # Configure Spawner
    # =========================================================================

    # Configure spawner class with all settings from config (single entry point)
    RemoteLabKubeSpawner.configure_from_config(config)

    c.JupyterHub.spawner_class = RemoteLabKubeSpawner

    # =========================================================================
    # Configure Authenticator
    # =========================================================================

    c.Authenticator.enable_auth_state = True
    c.Authenticator.auth_refresh_age = 3600  # check token refresh every hour

    async def auth_state_hook(spawner, auth_state):
        if auth_state is None:
            spawner.github_access_token = None
            return
        spawner.github_access_token = auth_state.get("access_token")

    c.Spawner.auth_state_hook = auth_state_hook

    # Set authenticator based on mode
    c.JupyterHub.authenticator_class = create_authenticator(config.auth_mode)

    if config.auth_mode == "auto-login":
        c.Authenticator.allow_all = True
    elif config.auth_mode == "multi":
        c.MultiAuthenticator.authenticators = [
            {
                "authenticator_class": CustomGitHubOAuthenticator,
                "url_prefix": "/github",
            },
            {
                "authenticator_class": CustomFirstUseAuthenticator,
                "url_prefix": "/native",
                "config": {"prefix": ""},
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
    )

    if not hasattr(c.JupyterHub, "extra_handlers") or c.JupyterHub.extra_handlers is None:
        c.JupyterHub.extra_handlers = []

    for route, handler in get_handlers():
        c.JupyterHub.extra_handlers.append((route, handler))

    # =========================================================================
    # Determine Database URL
    # =========================================================================

    from core import z2jh

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

    if config.quota_enabled:
        try:
            from core.quota import init_quota_manager
            from core.quota.migrate import check_migration_needed, migrate_quota_data

            # Check and run migration from old quota.sqlite if needed
            if check_migration_needed():
                print("[QUOTA] Migrating data from old quota.sqlite...")
                migrate_quota_data(db_url)

            quota_manager = init_quota_manager()
            stale_sessions = quota_manager.cleanup_stale_sessions()
            if stale_sessions:
                print(f"[QUOTA] Cleaned up {len(stale_sessions)} stale sessions on startup")
            active_count = quota_manager.get_active_sessions_count()
            print(f"[QUOTA] {active_count} active sessions found")
        except Exception as e:
            print(f"[QUOTA] Warning: Failed to initialize quota manager: {e}")

    # =========================================================================
    # API Token
    # =========================================================================

    api_token = os.environ.get("JUPYTERHUB_API_TOKEN")
    if api_token:
        c.JupyterHub.api_tokens = {api_token: "admin"}
        print("[SETUP] API token loaded for admin user")

    # =========================================================================
    # Template Paths
    # =========================================================================

    template_path = os.environ.get("JUPYTERHUB_TEMPLATE_PATH", "/tmp/custom_templates")
    c.JupyterHub.template_paths = [template_path]

    # =========================================================================
    # Auto-Create Admin User
    # =========================================================================

    admin_password = os.environ.get("JUPYTERHUB_ADMIN_PASSWORD", "")
    admin_username = "admin"

    if admin_password:
        c.Authenticator.admin_users = {admin_username}
        print(f"[SETUP] Admin user configured: {admin_username}")

        try:
            from core.authenticators.models import UserPassword
            from core.database import session_scope

            with session_scope() as session:
                user_pw = session.query(UserPassword).filter_by(username=admin_username).first()
                if user_pw:
                    print(f"[SETUP] Admin '{admin_username}' password already set")
                else:
                    password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt())
                    user_pw = UserPassword(
                        username=admin_username,
                        password_hash=password_hash,
                        force_change=False,
                    )
                    session.add(user_pw)
                    print(f"[SETUP] Admin '{admin_username}' password set automatically")
        except Exception as e:
            print(f"[SETUP] Warning: Failed to set admin password: {e}")

    # =========================================================================
    # Template Vars
    # =========================================================================

    if not isinstance(c.JupyterHub.template_vars, dict):
        c.JupyterHub.template_vars = {}
    c.JupyterHub.template_vars["authenticator_mode"] = config.auth_mode  # type: ignore[assignment]
    c.JupyterHub.template_vars["hide_logout"] = config.auth_mode == "auto-login"  # type: ignore[assignment]

    print(f"[SETUP] Hub setup complete: auth_mode={config.auth_mode}")
    print(f"[SETUP] template_vars: {c.JupyterHub.template_vars}")
