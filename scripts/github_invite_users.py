#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""
GitHub Organization User Invitation Script

Invite GitHub users to an organization and add them to specified teams
using the PyGithub library.

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
import os
import subprocess
import sys

from github import Github, GithubException

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


def get_github_token():
    """Return a GitHub token from GITHUB_TOKEN env var or `gh auth token`."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def main():
    """Invite users in GITHUB_USERS to the org and add them to TEAMS."""
    parser = argparse.ArgumentParser(
        description="Invite GitHub users to an organization and add them to teams"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without making API calls",
    )
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

    g = Github(token)
    org = g.get_organization(ORG_NAME)
    print(f"Organization: {org.login}")

    team_objects = []
    for team_slug in TEAMS:
        try:
            team = org.get_team_by_slug(team_slug)
            team_objects.append(team)
            print(f"  Team found: {team.name} (slug: {team.slug})")
        except GithubException as e:
            print(f"  Team not found: {team_slug} ({e.data.get('message', str(e))})")
            sys.exit(1)

    print(f"\nUsers to process: {len(GITHUB_USERS)}")
    print(f"Teams to assign: {', '.join(t.slug for t in team_objects)}")

    if args.dry_run:
        print("\n--- DRY RUN ---\n")

    results = {"invited": 0, "already_member": 0, "failed": 0}

    for username in GITHUB_USERS:
        print(f"\n{'='*50}")
        print(f"User: {username}")

        try:
            user = g.get_user(username)
        except GithubException:
            print(f"  GitHub user not found: {username}")
            results["failed"] += 1
            continue

        if args.dry_run:
            print(f"  [DRY RUN] Would invite {username} to {ORG_NAME} as member")
            for team in team_objects:
                print(f"  [DRY RUN] Would add {username} to team: {team.slug}")
            results["invited"] += 1
            continue

        try:
            org.invite_user(user=user, role="direct_member", teams=team_objects)
            print(f"  Invited {username} to {ORG_NAME}")
            results["invited"] += 1
        except GithubException as e:
            msg = e.data.get("message", str(e)) if isinstance(e.data, dict) else str(e)
            if e.status == 422:
                print(f"  Already a member or pending invitation: {username}")
                results["already_member"] += 1
                for team in team_objects:
                    try:
                        team.add_membership(member=user, role="member")
                        print(f"  Added {username} to team: {team.slug}")
                    except GithubException as te:
                        team_msg = te.data.get("message", str(te)) if isinstance(te.data, dict) else str(te)
                        print(f"  Failed to add to team {team.slug}: {team_msg}")
            else:
                print(f"  Failed to invite: {msg}")
                results["failed"] += 1

    print(f"\n{'='*50}")
    print("Results:")
    print(f"  Invited: {results['invited']}")
    print(f"  Already member (teams updated): {results['already_member']}")
    print(f"  Failed: {results['failed']}")


if __name__ == "__main__":
    main()
