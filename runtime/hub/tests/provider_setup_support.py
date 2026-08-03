import types

GITHUB_SETTINGS = {
    "hub.config.GitHubOAuthenticator.app_id": "app-id",
    "hub.config.GitHubOAuthenticator.installation_id": "installation-id",
    "hub.config.GitHubOAuthenticator.private_key": "private-key",
    "hub.config.GitHubOAuthenticator.private_key_file": "private-key-file",
    "hub.config.GitHubOAuthenticator.team_sync_ttl_seconds": 123,
}


def make_config(auth: object, access_policy: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        auth=auth,
        auth_mode=auth.effective_mode,
        resources=types.SimpleNamespace(effective_access_policy=access_policy),
        accelerators={},
        build_quota_rates=lambda: {},
        quota_enabled=True,
        quota=types.SimpleNamespace(minimumToStart=0, defaultQuota=0),
        teams=types.SimpleNamespace(mapping={"learners": ["cpu"]}),
        github_org_name="example-org",
        platform_display_name="AUP Learning Cloud",
        cluster_name="",
    )
