#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""
GitHub Organization User Invitation Script

This script invites GitHub users to an organization and adds them to specified
teams in a single API call, using only the Python standard library.

Features:
- Invite users to a GitHub organization as direct members
- Assign users to one or more teams at invitation time
- Fall back to team membership update if the user is already a member
- Dry-run mode to preview actions without making API calls
- List org members with their role and team memberships

Requirements:
- Python 3.9+
- A GitHub token with `admin:org` scope, provided via one of:
  - GITHUB_TOKEN environment variable (personal access token)
  - gh CLI authenticated with the required scope:
      Install: https://cli.github.com
      Authenticate: gh auth login
      Add required scope: gh auth refresh -s admin:org

Environment Variables:
- GITHUB_TOKEN: Personal access token with `admin:org` scope.
  If not set, the token is read automatically from `gh auth token`.

Configuration:
    Edit the following variables at the top of the script before running:
    - ORG_NAME: GitHub organization name to invite users to
    - GITHUB_USERS: list of GitHub usernames to invite
    - TEAMS: list of team slugs to assign to all invited users

Usage:
    # Invite users and add to teams
    python github_invite_users.py invite

    # Dry run (preview actions without making API calls)
    python github_invite_users.py invite --dry-run

    # List org members with their role and teams
    python github_invite_users.py list

    # List pending (unaccepted) invitations
    python github_invite_users.py pending
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# =============================================================================
# CONFIGURATION — Edit these values before running
# =============================================================================

ORG_NAME = "your-org-name"  # Replace with your GitHub organization name

GITHUB_USERS = [
    # "username1",
    # "username2",
]

TEAMS = ["code-cpu", "code-gpu", "cpu", "gpu", "npu", "official", "public"]

# =============================================================================

GITHUB_API = "https://api.github.com"


def print_table(headers, rows):
    """Print a simple aligned table without external dependencies."""
    widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*row))


def get_github_token():
    """Return a GitHub token from GITHUB_TOKEN env var or `gh auth token`."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def gh_request(token, method, path, body=None):
    """Make a GitHub API request and return the parsed JSON response."""
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def gh_paginate(token, path):
    """Fetch all pages of a GitHub API endpoint and return the combined list."""
    results = []
    url = f"{GITHUB_API}{path}?per_page=100"
    while url:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                results.extend(json.loads(resp.read()))
                link = resp.headers.get("Link", "")
                url = None
                for part in link.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
        except urllib.error.HTTPError as e:
            data = json.loads(e.read())
            print(f"  ❌ API error {e.code} on {path}: {data.get('message', str(e))}")
            return []
    return results


def cmd_invite(args, token):
    """Invite users in GITHUB_USERS to the org and add them to TEAMS."""
    if not GITHUB_USERS:
        print("No users specified. Edit GITHUB_USERS in the script.")
        sys.exit(1)

    if not TEAMS:
        print("No teams specified. Edit TEAMS in the script.")
        sys.exit(1)

    # Resolve team slugs to team IDs
    print(f"Organization: {ORG_NAME}")
    team_ids = {}
    for team_slug in TEAMS:
        status, data = gh_request(token, "GET", f"/orgs/{ORG_NAME}/teams/{team_slug}")
        if status == 200:
            team_ids[team_slug] = data["id"]
            print(f"  ✅ Team found: {data['name']} (slug: {team_slug})")
        else:
            print(f"  ❌ Team not found: {team_slug} ({data.get('message', status)})")
            sys.exit(1)

    print(f"\n🔄 Processing {len(GITHUB_USERS)} users...")
    print(f"   Teams to assign: {', '.join(team_ids)}")

    if args.dry_run:
        print("\n--- DRY RUN ---\n")

    results = {"invited": 0, "already_member": 0, "failed": 0}

    for username in GITHUB_USERS:
        print(f"\n{'=' * 50}")
        print(f"User: {username}")

        # Resolve username to numeric ID (required by the invitations endpoint)
        status, data = gh_request(token, "GET", f"/users/{username}")
        if status != 200:
            print(f"  ❌ GitHub user not found: {username}")
            results["failed"] += 1
            continue
        user_id = data["id"]

        if args.dry_run:
            print(f"  [DRY RUN] Would invite {username} (id={user_id}) to {ORG_NAME} as member")
            for team_slug in team_ids:
                print(f"  [DRY RUN] Would add {username} to team: {team_slug}")
            results["invited"] += 1
            continue

        status, data = gh_request(
            token,
            "POST",
            f"/orgs/{ORG_NAME}/invitations",
            {"invitee_id": user_id, "role": "direct_member", "team_ids": list(team_ids.values())},
        )
        if status == 201:
            print(f"  ✅ Invited {username} to {ORG_NAME}")
            results["invited"] += 1
        elif status == 422:
            print(f"  ⚠️  Already a member or pending invitation: {username}")
            results["already_member"] += 1
            for team_slug in team_ids:
                status, data = gh_request(token, "PUT", f"/orgs/{ORG_NAME}/teams/{team_slug}/memberships/{username}", {"role": "member"})
                if status == 200:
                    print(f"  ✅ Added {username} to team: {team_slug}")
                else:
                    print(f"  ❌ Failed to add to team {team_slug}: {data.get('message', status)}")
        else:
            print(f"  ❌ Failed to invite: {data.get('message', status)}")
            results["failed"] += 1

    print("\n" + "=" * 50)
    print("📊 Results:")
    print(f"  ✅ Invited: {results['invited']}")
    print(f"  ⚠️  Already member (teams updated): {results['already_member']}")
    print(f"  ❌ Failed: {results['failed']}")
    print("=" * 50)


def cmd_list(args, token):
    """List all org members with their role and team memberships."""
    print(f"🔄 Fetching members for {ORG_NAME}...")

    members = gh_paginate(token, f"/orgs/{ORG_NAME}/members")
    if not members:
        print("❌ No members returned. Check ORG_NAME and that your token has admin:org scope.")
        sys.exit(1)

    # Fetch all teams and their members once to avoid N*T API calls
    teams = gh_paginate(token, f"/orgs/{ORG_NAME}/teams")
    team_members = {}
    for team in teams:
        slug = team["slug"]
        members_in_team = gh_paginate(token, f"/orgs/{ORG_NAME}/teams/{slug}/members")
        for m in members_in_team:
            team_members.setdefault(m["login"], []).append(slug)

    # Fetch each member's org role
    rows = []
    for member in members:
        username = member["login"]
        _, membership = gh_request(token, "GET", f"/orgs/{ORG_NAME}/memberships/{username}")
        role = membership.get("role", "unknown")
        user_teams = ", ".join(sorted(team_members.get(username, []))) or "—"
        rows.append([username, role, user_teams])

    rows.sort(key=lambda r: r[0].lower())

    print(f"\n📋 Members: {len(rows)}\n")
    print_table(["Username", "Permission", "Teams"], rows)


def cmd_pending(args, token):
    """List all pending (unaccepted) invitations for the org."""
    print(f"🔄 Fetching pending invitations for {ORG_NAME}...")

    invitations = gh_paginate(token, f"/orgs/{ORG_NAME}/invitations")
    if not invitations:
        print("✅ No pending invitations.")
        return

    rows = []
    for inv in invitations:
        login = inv.get("login") or inv.get("email") or "—"
        created_at = (inv.get("created_at") or "—")[:10]
        rows.append([login, created_at])

    rows.sort(key=lambda r: r[0].lower())

    print(f"\n📋 Pending invitations: {len(rows)}\n")
    print_table(["Username / Email", "Invited On"], rows)


def main():
    """Entry point — dispatch to invite, list, or pending subcommand."""
    parser = argparse.ArgumentParser(description="GitHub organization user management")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    invite_parser = subparsers.add_parser("invite", help="Invite users to the org and assign to teams")
    invite_parser.add_argument("--dry-run", action="store_true", help="Preview actions without making API calls")

    subparsers.add_parser("list", help="List org members with their role and teams")
    subparsers.add_parser("pending", help="List pending (unaccepted) invitations")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    token = get_github_token()
    if not token:
        print("❌ No GitHub token found.")
        print("Set GITHUB_TOKEN env var or authenticate with: gh auth login")
        sys.exit(1)

    if args.command == "invite":
        cmd_invite(args, token)
    elif args.command == "list":
        cmd_list(args, token)
    elif args.command == "pending":
        cmd_pending(args, token)


if __name__ == "__main__":
    main()
