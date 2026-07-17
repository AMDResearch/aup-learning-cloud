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
Group Sync and Resource Resolution

Provides functions for:
- Fetching GitHub team memberships via API
- Syncing GitHub teams to JupyterHub groups (protected, source=github-team)
- Resolving user resources from JupyterHub group memberships
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

import aiohttp
import jwt
from jupyterhub.orm import Group as ORMGroup
from jupyterhub.user import User as JupyterHubUser
from sqlalchemy.orm import Session

from core.authenticators.github_app import GITHUB_USERNAME_PREFIX

log = logging.getLogger("jupyterhub.groups")

GITHUB_TEAM_SOURCE = "github-team"
SYSTEM_SOURCE = "system"
SYSTEM_GROUP_NAMES = {"github-users", "native-users"}
_GITHUB_TEAM_SYNC_CACHE: dict[tuple[str, str, str, str], tuple[float, list[str]]] = {}
_GITHUB_TEAM_SYNC_LOCKS: dict[str, asyncio.Lock] = {}
_GITHUB_TEAM_MEMBERS_CACHE: dict[tuple[str, str, str, tuple[str, ...]], tuple[float, dict[str, list[str]]]] = {}
_GITHUB_TEAM_MEMBERS_LOCK = asyncio.Lock()
_GITHUB_APP_INSTALLATION_ID_CACHE: dict[tuple[str, str], str] = {}
_GITHUB_APP_INSTALLATION_ID_LOCK = asyncio.Lock()
_GITHUB_APP_INSTALLATION_TOKEN: dict[tuple[str, str], tuple[str, float]] = {}
_GITHUB_APP_INSTALLATION_TOKEN_LOCK = asyncio.Lock()


def _github_team_sync_ttl(team_sync_ttl_seconds: int | str | None = None) -> int:
    if team_sync_ttl_seconds in (None, ""):
        return 3600
    with suppress(TypeError, ValueError):
        return max(0, int(team_sync_ttl_seconds))
    return 3600


def _github_app_private_key(private_key: str = "", private_key_file: str = "") -> str:
    private_key_file = private_key_file.strip()
    if private_key_file:
        try:
            with open(private_key_file) as f:
                return f.read()
        except OSError as e:
            log.warning("Unable to read GitHub App private key file %s: %s", private_key_file, e)
            return ""
    return private_key.replace("\\n", "\n").strip()


def _github_team_api_slug(team_key: str) -> str:
    """Convert a configured group/team key to the GitHub team slug API form."""
    return team_key.strip().lower().replace(" ", "-")


async def get_github_app_installation_token(
    app_id: str,
    installation_id: str = "",
    org_name: str = "",
    *,
    private_key: str = "",
    private_key_file: str = "",
) -> str | None:
    """Create or reuse a GitHub App installation access token for group sync."""
    resolved_installation_id = await _resolve_github_app_installation_id(
        app_id,
        installation_id,
        org_name,
        private_key=private_key,
        private_key_file=private_key_file,
    )
    if not resolved_installation_id:
        return None

    now = time.time()
    cache_key = (app_id, resolved_installation_id)
    cached_token = _GITHUB_APP_INSTALLATION_TOKEN.get(cache_key)
    if cached_token and now < cached_token[1] - 300:
        return cached_token[0]

    async with _GITHUB_APP_INSTALLATION_TOKEN_LOCK:
        now = time.time()
        cached_token = _GITHUB_APP_INSTALLATION_TOKEN.get(cache_key)
        if cached_token and now < cached_token[1] - 300:
            return cached_token[0]

        private_key = _github_app_private_key(private_key=private_key, private_key_file=private_key_file)
        if not app_id or not resolved_installation_id or not private_key:
            log.warning(
                "GitHub App installation token is unavailable because app id, installation id, or private key is missing"
            )
            return None

        app_jwt = jwt.encode(
            {"iat": int(now) - 60, "exp": int(now) + 540, "iss": app_id},
            private_key,
            algorithm="RS256",
        )
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    f"https://api.github.com/app/installations/{resolved_installation_id}/access_tokens",
                    headers=headers,
                ) as resp,
            ):
                if resp.status != 201:
                    log.warning("GitHub App installation token request returned status %d", resp.status)
                    return None
                data = await resp.json()
        except Exception as e:
            log.warning("Error creating GitHub App installation token: %s", e)
            return None

        token = data.get("token")
        expires_at = data.get("expires_at")
        if not token:
            log.warning("GitHub App installation token response did not include a token")
            return None

        expires_ts = now + 3600
        if isinstance(expires_at, str):
            from datetime import datetime

            with suppress(ValueError):
                expires_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()

        _GITHUB_APP_INSTALLATION_TOKEN[cache_key] = (token, expires_ts)
        return token


async def _resolve_github_app_installation_id(
    app_id: str,
    installation_id: str,
    org_name: str,
    *,
    private_key: str = "",
    private_key_file: str = "",
) -> str | None:
    installation_id = installation_id.strip()
    if installation_id:
        return installation_id

    org_name = org_name.strip()
    if not app_id or not org_name:
        log.warning("GitHub App installation ID lookup is unavailable because app id or org name is missing")
        return None

    cache_key = (app_id, org_name)
    cached_installation_id = _GITHUB_APP_INSTALLATION_ID_CACHE.get(cache_key)
    if cached_installation_id:
        return cached_installation_id

    async with _GITHUB_APP_INSTALLATION_ID_LOCK:
        cached_installation_id = _GITHUB_APP_INSTALLATION_ID_CACHE.get(cache_key)
        if cached_installation_id:
            return cached_installation_id

        private_key = _github_app_private_key(private_key=private_key, private_key_file=private_key_file)
        if not private_key:
            log.warning("GitHub App installation ID lookup is unavailable because the private key is missing")
            return None

        now = time.time()
        app_jwt = jwt.encode(
            {"iat": int(now) - 60, "exp": int(now) + 540, "iss": app_id},
            private_key,
            algorithm="RS256",
        )
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"https://api.github.com/orgs/{org_name}/installation",
                    headers=headers,
                ) as resp,
            ):
                if resp.status == 404:
                    log.warning("GitHub App installation lookup returned 404 for org %s", org_name)
                    return None
                if resp.status != 200:
                    log.warning(
                        "GitHub App installation lookup returned status %d for org %s",
                        resp.status,
                        org_name,
                    )
                    return None
                data = await resp.json()
        except Exception as e:
            log.warning("Error resolving GitHub App installation for org %s: %s", org_name, e)
            return None

        resolved_installation_id = data.get("id")
        if resolved_installation_id is None:
            log.warning(
                "GitHub App installation lookup for org %s did not include an installation id",
                org_name,
            )
            return None

        resolved_installation_id = str(resolved_installation_id)
        _GITHUB_APP_INSTALLATION_ID_CACHE[cache_key] = resolved_installation_id
        return resolved_installation_id


async def fetch_github_team_members(access_token: str, org_name: str, team_slug: str) -> set[str] | None:
    """Fetch all GitHub usernames in one team using the configured platform token."""
    if not access_token or not org_name or not team_slug:
        return set()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    members: set[str] = set()
    page = 1
    try:
        async with aiohttp.ClientSession() as session:
            while True:
                url = f"https://api.github.com/orgs/{org_name}/teams/{team_slug}/members?per_page=100&page={page}"
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 404:
                        log.warning(
                            "GitHub API returned status 404 when fetching members for team %s in org %s",
                            team_slug,
                            org_name,
                        )
                        return set()
                    if resp.status != 200:
                        log.warning(
                            "GitHub API returned status %d when fetching members for team %s in org %s",
                            resp.status,
                            team_slug,
                            org_name,
                        )
                        return None
                    data = await resp.json()

                for member in data:
                    login = member.get("login")
                    if isinstance(login, str) and login:
                        members.add(login.lower())

                if len(data) < 100:
                    break
                page += 1
    except Exception as e:
        log.warning("Error fetching GitHub team members for %s: %s", team_slug, e)
        return None

    return members


def _build_github_team_members_graphql_query(team_count: int) -> str:
    variable_defs = ["$org: String!"]
    team_fields = []
    for index in range(team_count):
        variable_defs.extend([f"$slug{index}: String!", f"$after{index}: String"])
        team_fields.append(
            f"""
      team{index}: team(slug: $slug{index}) {{
        members(first: 100, after: $after{index}) {{
          nodes {{
            login
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
      }}"""
        )

    return f"""
query({", ".join(variable_defs)}) {{
  organization(login: $org) {{
{"".join(team_fields)}
  }}
}}
"""


_GITHUB_ORG_TEAMS_GRAPHQL_QUERY = """
query($org: String!, $after: String) {
  organization(login: $org) {
    teams(first: 100, after: $after) {
      nodes {
        name
        slug
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


async def fetch_github_org_team_slugs_graphql(access_token: str, org_name: str) -> set[str] | None:
    """Fetch all team slugs that actually exist in a GitHub organization."""
    if not access_token or not org_name:
        return set()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    team_slugs: set[str] = set()
    after: str | None = None

    try:
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": _GITHUB_ORG_TEAMS_GRAPHQL_QUERY, "variables": {"org": org_name, "after": after}},
                ) as resp:
                    if resp.status != 200:
                        log.warning("GitHub GraphQL API returned status %d when fetching org teams", resp.status)
                        return None
                    data = await resp.json()

                if data.get("errors"):
                    log.warning("GitHub GraphQL API returned errors when fetching org teams: %s", data["errors"])
                    return None

                organization = data.get("data", {}).get("organization")
                if organization is None:
                    log.warning("GitHub GraphQL API did not return organization %s", org_name)
                    return None

                teams = organization.get("teams") or {}
                for team in teams.get("nodes") or []:
                    slug = team.get("slug") if isinstance(team, dict) else None
                    if isinstance(slug, str) and slug:
                        team_slugs.add(slug)

                page_info = teams.get("pageInfo") or {}
                if not page_info.get("hasNextPage"):
                    break
                after = page_info.get("endCursor")
    except Exception as e:
        log.warning("Error fetching GitHub org teams with GraphQL for org %s: %s", org_name, e)
        return None

    return team_slugs


async def fetch_github_team_members_table_graphql(
    access_token: str,
    org_name: str,
    team_keys: list[str],
) -> dict[str, list[str]] | None:
    """Fetch a login -> configured team-key table with batched GraphQL team queries."""
    if not access_token or not org_name or not team_keys:
        return {}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    teams_by_login: dict[str, list[str]] = {}
    actual_team_slugs = await fetch_github_org_team_slugs_graphql(access_token, org_name)
    if actual_team_slugs is None:
        return None

    existing_team_keys = []
    for team_key in team_keys:
        api_slug = _github_team_api_slug(team_key)
        if api_slug in actual_team_slugs:
            existing_team_keys.append(team_key)
        else:
            log.warning("GitHub org %s does not have configured team %s", org_name, api_slug)

    pending = dict.fromkeys(existing_team_keys)

    try:
        async with aiohttp.ClientSession() as session:
            while pending:
                batch_keys = list(pending)
                variables: dict[str, str | None] = {"org": org_name}
                for index, team_key in enumerate(batch_keys):
                    variables[f"slug{index}"] = _github_team_api_slug(team_key)
                    variables[f"after{index}"] = pending[team_key]

                async with session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={
                        "query": _build_github_team_members_graphql_query(len(batch_keys)),
                        "variables": variables,
                    },
                ) as resp:
                    if resp.status != 200:
                        log.warning("GitHub GraphQL API returned status %d when fetching team members", resp.status)
                        return None
                    data = await resp.json()

                if data.get("errors"):
                    log.warning("GitHub GraphQL API returned errors when fetching team members: %s", data["errors"])
                    return None

                organization = data.get("data", {}).get("organization")
                if organization is None:
                    log.warning("GitHub GraphQL API did not return organization %s", org_name)
                    return None

                next_pending: dict[str, str | None] = {}
                for index, team_key in enumerate(batch_keys):
                    team = organization.get(f"team{index}")
                    if team is None:
                        log.warning(
                            "GitHub GraphQL API did not return team %s in org %s",
                            _github_team_api_slug(team_key),
                            org_name,
                        )
                        continue

                    members = team.get("members") or {}
                    for member in members.get("nodes") or []:
                        login = member.get("login") if isinstance(member, dict) else None
                        if isinstance(login, str) and login:
                            teams_by_login.setdefault(login.lower(), []).append(team_key)

                    page_info = members.get("pageInfo") or {}
                    if page_info.get("hasNextPage"):
                        next_pending[team_key] = page_info.get("endCursor")

                pending = next_pending
    except Exception as e:
        log.warning("Error fetching GitHub team members with GraphQL for org %s: %s", org_name, e)
        return None

    return teams_by_login


async def fetch_github_team_members_table(
    app_id: str,
    installation_id: str,
    private_key: str,
    private_key_file: str,
    org_name: str,
    team_slugs: set[str],
    *,
    team_sync_ttl_seconds: int | str | None = None,
    force: bool = False,
) -> dict[str, list[str]] | None:
    """Fetch a login -> team-slugs table using one GitHub request sequence per team."""
    github_team_keys = sorted(team_slugs - SYSTEM_GROUP_NAMES)
    if not app_id or not org_name or not github_team_keys:
        return {}

    cache_key = (app_id, installation_id, org_name, tuple(github_team_keys))
    now = time.time()
    ttl = _github_team_sync_ttl(team_sync_ttl_seconds)
    cached = _GITHUB_TEAM_MEMBERS_CACHE.get(cache_key)
    if not force and cached and now - cached[0] < ttl:
        return {login: list(teams) for login, teams in cached[1].items()}

    async with _GITHUB_TEAM_MEMBERS_LOCK:
        now = time.time()
        cached = _GITHUB_TEAM_MEMBERS_CACHE.get(cache_key)
        if not force and cached and now - cached[0] < ttl:
            return {login: list(teams) for login, teams in cached[1].items()}

        installation_token = await get_github_app_installation_token(
            app_id,
            installation_id,
            org_name=org_name,
            private_key=private_key,
            private_key_file=private_key_file,
        )
        if not installation_token:
            return None

        teams_by_login = await fetch_github_team_members_table_graphql(
            installation_token,
            org_name,
            github_team_keys,
        )
        if teams_by_login is None:
            return None

        _GITHUB_TEAM_MEMBERS_CACHE[cache_key] = (now, teams_by_login)
        return {login: list(teams) for login, teams in teams_by_login.items()}


async def sync_github_teams_for_user(
    user: JupyterHubUser,
    app_id: str,
    installation_id: str,
    private_key: str,
    private_key_file: str,
    org_name: str,
    valid_mapping_keys: set[str],
    db: Session,
    *,
    team_sync_ttl_seconds: int | str | None = None,
    force: bool = False,
) -> bool:
    """Sync one GitHub user's teams with the configured platform token.

    The throttle and per-user lock live here so every caller shares the same
    protection. Concurrent spawns for the same user coalesce into one set of
    GitHub team membership checks within the TTL window.
    """
    if not user.name.startswith(GITHUB_USERNAME_PREFIX) or not app_id:
        return False

    lock = _GITHUB_TEAM_SYNC_LOCKS.setdefault(user.name, asyncio.Lock())
    async with lock:
        now = time.time()
        ttl = _github_team_sync_ttl(team_sync_ttl_seconds)
        cache_key = (user.name, app_id, installation_id, org_name)
        cached = _GITHUB_TEAM_SYNC_CACHE.get(cache_key)
        if not force and cached and now - cached[0] < ttl:
            team_slugs = cached[1]
        else:
            github_username = user.name.split(":", 1)[1]
            teams_by_login = await fetch_github_team_members_table(
                app_id,
                installation_id,
                private_key,
                private_key_file,
                org_name,
                valid_mapping_keys,
                team_sync_ttl_seconds=team_sync_ttl_seconds,
                force=force,
            )
            if teams_by_login is None:
                return False
            team_slugs = teams_by_login.get(github_username.lower(), [])
            _GITHUB_TEAM_SYNC_CACHE[cache_key] = (now, team_slugs)

        sync_user_github_teams(user, team_slugs, valid_mapping_keys, db)
        return True


def sync_user_github_teams(
    user: JupyterHubUser,
    team_slugs: list[str] | None,
    valid_mapping_keys: set[str],
    db: Session,
) -> None:
    """Sync a user's GitHub team memberships to JupyterHub groups.

    For each team slug that exists in ``valid_mapping_keys``, ensures
    a JupyterHub group exists with ``properties.source = "github-team"``
    and adds the user to it. Removes the user from any github-team groups
    they no longer belong to.

    Args:
        user: JupyterHub User object.
        team_slugs: Team slugs the user currently belongs to on GitHub.
        valid_mapping_keys: Set of group names that have resource mappings in config.
        db: JupyterHub database session (``self.db`` from a handler or hook).
    """
    if team_slugs is None:
        log.warning("Skipping github-team sync for user '%s' because team membership could not be fetched", user.name)
        return

    relevant_teams = set(team_slugs) & valid_mapping_keys
    assert user.orm_user is not None  # populated by JupyterHub on init

    # Ensure groups exist and add user
    for team_slug in relevant_teams:
        orm_group = db.query(ORMGroup).filter_by(name=team_slug).first()
        if orm_group is None:
            orm_group = ORMGroup(name=team_slug)
            orm_group.properties = {"source": GITHUB_TEAM_SOURCE}  # type: ignore[assignment]
            db.add(orm_group)
            db.commit()
            log.info("Created JupyterHub group '%s' (source: github-team)", team_slug)
        elif orm_group.properties.get("source") != GITHUB_TEAM_SOURCE:
            # GitHub team always takes priority over admin-created groups
            orm_group.properties = {**orm_group.properties, "source": GITHUB_TEAM_SOURCE}  # type: ignore[assignment]
            db.commit()
            log.info("Group '%s' promoted to github-team source", team_slug)

        # Add user to group if not already a member
        if orm_group not in user.orm_user.groups:
            user.orm_user.groups.append(orm_group)
            db.commit()
            log.info("Added user '%s' to group '%s'", user.name, team_slug)

    # Remove user from github-team groups they no longer belong to
    for orm_group in list(user.orm_user.groups):
        if orm_group.properties.get("source") == GITHUB_TEAM_SOURCE and orm_group.name not in relevant_teams:
            user.orm_user.groups.remove(orm_group)
            db.commit()
            log.info("Removed user '%s' from group '%s'", user.name, orm_group.name)


def assign_user_to_group(
    user: JupyterHubUser,
    group_name: str,
    db: Session,
) -> None:
    """Assign a user to a JupyterHub group, creating it if needed.

    Used for native users to assign them to pattern-based groups.

    Args:
        user: JupyterHub User object.
        group_name: Name of the group to assign to.
        db: JupyterHub database session.
    """
    assert user.orm_user is not None  # populated by JupyterHub on init

    orm_group = db.query(ORMGroup).filter_by(name=group_name).first()
    if orm_group is None:
        orm_group = ORMGroup(name=group_name)
        orm_group.properties = {"source": SYSTEM_SOURCE}  # type: ignore[assignment]
        db.add(orm_group)
        db.commit()
        log.info("Created JupyterHub group '%s' (source: system)", group_name)
    elif not orm_group.properties.get("source"):
        orm_group.properties = {**orm_group.properties, "source": SYSTEM_SOURCE}  # type: ignore[assignment]
        db.commit()

    if orm_group not in user.orm_user.groups:
        user.orm_user.groups.append(orm_group)
        db.commit()
        log.info("Added user '%s' to group '%s'", user.name, group_name)


def get_resources_for_user(
    user: JupyterHubUser,
    team_resource_mapping: dict[str, list[str]],
) -> list[str]:
    """Get available resources for a user based on their JupyterHub group memberships.

    Iterates over the user's groups and looks up each group name in the
    ``team_resource_mapping``. If a group maps to ``"official"``, the full
    official resource list is returned immediately (short-circuit).

    Args:
        user: JupyterHub User object.
        team_resource_mapping: Mapping of group/team names to resource lists.

    Returns:
        Deduplicated list of resource names the user can access.
    """
    assert user.orm_user is not None  # populated by JupyterHub on init
    user_group_names = {g.name for g in user.orm_user.groups}
    available_resources: list[str] = []

    for group_name in user_group_names:
        if group_name not in team_resource_mapping:
            continue
        available_resources.extend(team_resource_mapping[group_name])

    # Deduplicate while preserving order
    return list(dict.fromkeys(available_resources))


def resolve_resources_for_user(
    user: JupyterHubUser,
    team_resource_mapping: dict[str, list[str]],
    auth_mode: str,
    all_resources: list[str],
) -> list[str]:
    """Resolve the resources visible to a user for UI and spawn flows."""
    username = user.name.strip()

    if auth_mode in ["auto-login", "dummy"]:
        return all_resources

    available_resources = get_resources_for_user(user, team_resource_mapping)
    if available_resources:
        return available_resources

    if not username.startswith(GITHUB_USERNAME_PREFIX):
        return team_resource_mapping.get("native-users", team_resource_mapping.get("official", []))

    return ["none"]


def is_readonly_group(group: ORMGroup) -> bool:
    """Check if a group's membership is fully read-only.

    Only system-managed groups are fully read-only.  GitHub-team groups
    allow manual member additions (admins can add native users to grant
    them the same resources).  Synced GitHub members are auto-managed:
    they may be re-added or removed on the next login sync.

    Args:
        group: JupyterHub ORM Group object.

    Returns:
        True if the group's source is "system".
    """
    return group.properties.get("source") == SYSTEM_SOURCE  # type: ignore[union-attr]


def is_undeletable_group(group: ORMGroup) -> bool:
    """Check if a group cannot be deleted.

    Both GitHub-synced groups and system-managed groups are undeletable.

    Args:
        group: JupyterHub ORM Group object.

    Returns:
        True if the group's source is "github-team" or "system".
    """
    return group.properties.get("source") in (GITHUB_TEAM_SOURCE, SYSTEM_SOURCE)  # type: ignore[union-attr]
