#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""
GitHub Organization User Invitation Script

Invite GitHub users to an organization and add them to specified teams.
Uses only Python standard library — no third-party dependencies required.

Authentication:
    Set GITHUB_TOKEN environment variable with a token that has `admin:org` scope.
    If not set, the script will try to read the token from `gh auth token`.

Usage:
    # Dry run (preview actions without making API calls)
    python github_invite_users.py --dry-run

    # Invite users and add to teams
    python github_invite_users.py
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


def main():
    """Invite users in GITHUB_USERS to the org and add them to TEAMS."""

    parser = argparse.ArgumentParser(description="Invite GitHub users to an organization and add them to teams")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without making API calls")
    args = parser.parse_args()

    if not GITHUB_USERS:
        print("No users specified. Edit GITHUB_USERS in the script.")
        sys.exit(1)

    if not TEAMS:
        print("No teams specified. Edit TEAMS in the script.")
        sys.exit(1)

    token = get_github_token()
    if not token:
        print("No GitHub token found.")
        print("Set GITHUB_TOKEN env var or authenticate with: gh auth login")
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


if __name__ == "__main__":
    main()
